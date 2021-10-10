#include "config.h"

#include <string>
#include <set>
#include <algorithm>

#include <clang/ASTMatchers/ASTMatchFinder.h>
#include <clang/ASTMatchers/ASTMatchers.h>
#include <clang/Analysis/CFG.h>
#include <clang/Analysis/Analyses/Dominators.h>
#include <clang/Frontend/FrontendActions.h>
#include <clang/Tooling/CommonOptionsParser.h>
#include <clang/Tooling/Tooling.h>
#include <clang/Tooling/JSONCompilationDatabase.h>
#include <llvm/Support/CommandLine.h>

using namespace clang;
using namespace clang::ast_matchers;
using namespace clang::tooling;

using namespace llvm;

static cl::OptionCategory MyToolCategory("dom options");

static cl::opt<std::string> build_path("p", cl::desc("Build path that contains a compile_commands.json"), cl::Required, cl::cat(MyToolCategory));

static cl::opt<std::string> src_name("source", cl::desc("Source file"), cl::Required, cl::cat(MyToolCategory));

static cl::opt<unsigned> line_num("line", cl::desc("Line number"), cl::Required, cl::cat(MyToolCategory));

static cl::opt<int> mode("mode", cl::desc("0 = any, 1 = pre, 2 = post, 3 = both"), cl::Required, cl::cat(MyToolCategory));

static cl::opt<bool> verbose("verbose", cl::desc("Show more information"), cl::init(false), cl::cat(MyToolCategory));

static cl::extrahelp MoreHelp("\nGet succeeding line numbers that are domintating (mode 2) or dominated (mode 1) by the current line.\n");

bool inside_range(const SourceManager *sm, const SourceRange &range, bool include_begin = true)
{
    unsigned begin_line = sm->getExpansionLineNumber(range.getBegin());
    unsigned end_line = sm->getExpansionLineNumber(range.getEnd());
    if (include_begin)
        return begin_line <= line_num && line_num <= end_line;
    else
        return begin_line < line_num && line_num <= end_line;
}

class DomAnalysis
{
private:
    const SourceManager *sm;
    const ASTContext *context;

    CFGBlock *find_block(CFG *cfg, unsigned line_num)
    {
        for (auto block : *cfg)
            for (auto elem : *block)
            {
                if (elem.getKind() != CFGElement::Statement)
                    continue;
                auto stmt = elem.castAs<CFGStmt>().getStmt();
                if (inside_range(sm, stmt->getSourceRange()))
                    return block;
            }
        return nullptr;
    }

    std::set<unsigned> get_lines_after(CFGBlock *cur_block, CFGBlock *block)
    {
        std::set<unsigned> lines;
        for (auto elem : *block)
        {
            if (elem.getKind() != CFGElement::Statement)
                continue;
            auto stmt = elem.castAs<CFGStmt>().getStmt();
            auto range = stmt->getSourceRange();
            unsigned begin_line = sm->getExpansionLineNumber(range.getBegin());
            unsigned end_line = sm->getExpansionLineNumber(range.getEnd());
            for (auto i = begin_line; i <= end_line; ++i)
            {
                if (block == cur_block && i <= line_num)
                    continue;
                lines.insert(i);
            }
        }
        return lines;
    }

    std::set<unsigned> check_dom(const CFGDomTree &dom_pre, const CFGPostDomTree &dom_post, CFGBlock *cur_block, CFGBlock *block)
    {
        std::set<unsigned> lines;
        if (mode == 0)
        {
            if (dom_pre.dominates(cur_block, block) || dom_post.dominates(block, cur_block))
                lines = get_lines_after(cur_block, block);
        }
        else if (mode == 1)
        {
            if (dom_pre.dominates(cur_block, block))
                lines = get_lines_after(cur_block, block);
        }
        else if (mode == 2)
        {
            if (dom_post.dominates(block, cur_block))
                lines = get_lines_after(cur_block, block);
        }
        else if (mode == 3)
        {
            if (dom_pre.dominates(cur_block, block) && dom_post.dominates(block, cur_block))
                lines = get_lines_after(cur_block, block);
        }
        return lines;
    }

public:
    DomAnalysis(const SourceManager *src_man, const ASTContext *ast_context)
        : sm(src_man), context(ast_context) {}

    void run(CFG *cfg)
    {
        if (verbose)
            cfg->dump(LangOptions(), true);

        auto cur_block = find_block(cfg, line_num);
        if (cur_block == nullptr)
            return;

        if (verbose)
            cur_block->dump();

        CFGDomTree dom_pre(cfg);
        CFGPostDomTree dom_post(cfg);

        std::set<unsigned> lines;
        for (auto block : *cfg)
        {
            auto new_lines = check_dom(dom_pre, dom_post, cur_block, block);
            lines.insert(new_lines.begin(), new_lines.end());
        }

        for (auto i : lines)
            llvm::outs() << i << "\n";
    }
};

class NewFuncAction : public MatchFinder::MatchCallback
{
private:
    CFG::BuildOptions cfg_options;

public:
    void run(const MatchFinder::MatchResult &result) override
    {
        auto func_decl = result.Nodes.getNodeAs<FunctionDecl>("funcDecl");
        if (func_decl == nullptr)
            return;

        auto sm = result.SourceManager;
        auto func_range = func_decl->getSourceRange();
        if (!sm->isInMainFile(func_range.getBegin()))
            return;

        if (!inside_range(sm, func_range))
            return;

        if (verbose)
        {
            llvm::outs() << "Function: " << func_decl->getNameAsString() << "\n";
            llvm::outs() << "Range: " << func_range.printToString(*sm) << "\n";
        }

        auto context = result.Context;
        auto body = func_decl->getBody();
        auto cfg = CFG::buildCFG(func_decl, body, context, cfg_options);
        if (cfg == nullptr) {
            if (verbose)
                llvm::outs() << "Cannot build cfg\n";
            return;
        }
        DomAnalysis analyzer(sm, context);
        analyzer.run(cfg.get());
    }
};

class DomASTConsumer : public ASTConsumer
{
private:
    MatchFinder match_finder;
    std::unique_ptr<NewFuncAction> act_func;

public:
    DomASTConsumer()
    {
        act_func = std::unique_ptr<NewFuncAction>(new NewFuncAction());
        match_finder.addMatcher(
            functionDecl().bind("funcDecl"),
            act_func.get());
    }

    void HandleTranslationUnit(ASTContext &context) override
    {
        match_finder.matchAST(context);
    }
};

class DomFrontend : public ASTFrontendAction
{
public:
    std::unique_ptr<ASTConsumer> CreateASTConsumer(
        CompilerInstance &CI, StringRef file) override
    {
        return std::unique_ptr<DomASTConsumer>(new DomASTConsumer());
    }
};

int main(int argc, char *argv[])
{
    cl::HideUnrelatedOptions(MyToolCategory);
    cl::ParseCommandLineOptions(argc, argv);

    std::string err_msg;
    auto compile_db = JSONCompilationDatabase::loadFromDirectory(build_path, err_msg);
    if (compile_db == nullptr)
    {
        llvm::errs() << err_msg << "\n";
        return EXIT_FAILURE;
    }

    ClangTool Tool(*compile_db, {src_name});

    ArgumentsAdjuster incl_adj = getInsertArgumentAdjuster("-isystem" STDINC, ArgumentInsertPosition::BEGIN);
    Tool.appendArgumentsAdjuster(incl_adj);

    return Tool.run(newFrontendActionFactory<DomFrontend>().get());
}