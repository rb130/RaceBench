cmake_minimum_required(VERSION 3.4.3)
project(dom)

find_package(LLVM REQUIRED CONFIG)
find_package(Clang REQUIRED CONFIG)

#list(APPEND CMAKE_MODULE_PATH ${LLVM_DIR})

#include(AddLLVM)
#include(HandleLLVMOptions)

#set(LLVM_LINK_COMPONENTS support)
#set(CMAKE_VERBOSE_MAKEFILE True)

set(CMAKE_EXPORT_COMPILE_COMMANDS True)

set(CMAKE_BUILD_TYPE Release)

include_directories(${LLVM_INCLUDE_DIRS})
include_directories(${CLANG_INCLUDE_DIRS})

link_directories(${LLVM_LIBRARY_DIRS})
link_directories(${CLANG_LIBRARY_DIRS})

set(STDINC "${CLANG_INSTALL_PREFIX}/lib/clang/${LLVM_PACKAGE_VERSION}/include")
configure_file(config.h.in config.h)

add_executable(dom
    dom.cpp
    config.h
)

target_link_libraries(dom PRIVATE
  clang-cpp
  LLVM
)
