cmake_minimum_required(VERSION 3.13.0)
project(kaldi_binaries)

include(ExternalProject)
include(ProcessorCount)

ProcessorCount(NCPU)
if(NOT NCPU EQUAL 0)
  set(MAKE_FLAGS -j${NCPU})
endif()

set(DST ${PROJECT_SOURCE_DIR}/kaldi_active_grammar/exec)
if ("${CMAKE_HOST_SYSTEM_NAME}" STREQUAL "Darwin")
  set(DST ${DST}/macos/)
elseif("${CMAKE_HOST_SYSTEM_NAME}" STREQUAL "Linux")
  set(DST ${DST}/linux/)
else()
  set(DST ${DST}/windows/)
endif()

set(BINARIES
  )
set(LIBRARIES
  src/lib/libkaldi-dragonfly${CMAKE_SHARED_LIBRARY_SUFFIX}
  )

if("${CMAKE_HOST_SYSTEM_NAME}" STREQUAL "Windows")
  message(FATAL_ERROR "CMake build not supported on Windows")
  # FIXME: copy files?
  # https://cmake.org/cmake/help/latest/command/foreach.html
  # https://stackoverflow.com/questions/34799916/copy-file-from-source-directory-to-binary-directory-using-cmake
endif()

find_program(MAKE_EXE NAMES make gmake nmake)

if(DEFINED ENV{INTEL_MKL_DIR})
  # Default: INTEL_MKL_DIR=/opt/intel/mkl/
  message("Compiling with MKL in: $ENV{INTEL_MKL_DIR}")
  set(KALDI_CONFIG_FLAGS --shared --static-math --use-cuda=no --mathlib=MKL --mkl-root=$ENV{INTEL_MKL_DIR})
  set(MATHLIB_BUILD_COMMAND true)
else()
  if(NOT DEFINED OPENBLAS_REF)
    if("${CMAKE_HOST_SYSTEM_NAME}" STREQUAL "Darwin")
      # Need newer version to build on macOS
      set(OPENBLAS_REF "v0.3.30")
    else()
      set(OPENBLAS_REF "v0.3.13")
    endif()
  endif()
  message("Compiling with OpenBLAS git ref: ${OPENBLAS_REF}")
  set(KALDI_CONFIG_FLAGS --shared --static-math --use-cuda=no --mathlib=OPENBLAS)
  set(MATHLIB_BUILD_COMMAND cd tools
    && git clone -b ${OPENBLAS_REF} --single-branch https://github.com/OpenMathLib/OpenBLAS
    && ${MAKE_EXE} ${MAKE_FLAGS} -C OpenBLAS DYNAMIC_ARCH=1 TARGET=GENERIC USE_LOCKING=1 USE_THREAD=0 all
    && ${MAKE_EXE} ${MAKE_FLAGS} -C OpenBLAS PREFIX=install install
    && cd ..)
endif()

if(DEFINED ENV{KALDI_BRANCH})
  set(KALDI_BRANCH $ENV{KALDI_BRANCH})
else()
  message(FATAL_ERROR "KALDI_BRANCH not set! Use 'origin/master'?")
  # set(KALDI_BRANCH "origin/master")
endif()

message("MAKE_EXE                  = ${MAKE_EXE}")
message("PYTHON_EXECUTABLE         = ${PYTHON_EXECUTABLE}")
message("PYTHON_INCLUDE_DIR        = ${PYTHON_INCLUDE_DIR}")
message("PYTHON_LIBRARY            = ${PYTHON_LIBRARY}")
message("PYTHON_VERSION_STRING     = ${PYTHON_VERSION_STRING}")
message("SKBUILD                   = ${SKBUILD}")
message("KALDI_BRANCH              = ${KALDI_BRANCH}")
message("CMAKE_CURRENT_SOURCE_DIR  = ${CMAKE_CURRENT_SOURCE_DIR}")
message("CMAKE_CURRENT_BINARY_DIR  = ${CMAKE_CURRENT_BINARY_DIR}")

# CXXFLAGS are set and exported in kaldi-configure-wrapper.sh

if(NOT "${CMAKE_HOST_SYSTEM_NAME}" STREQUAL "Windows")
  set(STRIP_LIBS_COMMAND find src/lib tools/openfst/lib -name *${CMAKE_SHARED_LIBRARY_SUFFIX} | xargs strip)
  # set(STRIP_DST_COMMAND find ${DST} [[[other specifiers]]] | xargs strip)
  if("${CMAKE_HOST_SYSTEM_NAME}" STREQUAL "Darwin")
    list(APPEND STRIP_LIBS_COMMAND -x)
    # list(APPEND STRIP_DST_COMMAND -x)
  endif()
  # set(STRIP_LIBS_COMMAND true)
  set(STRIP_DST_COMMAND true)
  ExternalProject_Add(kaldi
    GIT_CONFIG        advice.detachedHead=false
    GIT_REPOSITORY    https://github.com/daanzu/kaldi-fork-active-grammar.git
    GIT_TAG           ${KALDI_BRANCH}
    GIT_SHALLOW       TRUE
    CONFIGURE_COMMAND sed -i.bak -e "s/status=0/exit 0/g" tools/extras/check_dependencies.sh && sed -i.bak -e "s/openfst_add_CXXFLAGS = -g -O2/openfst_add_CXXFLAGS = -g0 -O3/g" tools/Makefile && cp ${PROJECT_SOURCE_DIR}/building/kaldi-configure-wrapper.sh src/
    BUILD_IN_SOURCE   TRUE
    BUILD_COMMAND     ${MATHLIB_BUILD_COMMAND} && cd tools && ${MAKE_EXE} && cd openfst && autoreconf && cd ../../src && bash ./kaldi-configure-wrapper.sh ./configure ${KALDI_CONFIG_FLAGS} && ${MAKE_EXE} ${MAKE_FLAGS} depend && ${MAKE_EXE} ${MAKE_FLAGS} dragonfly
    LIST_SEPARATOR    " "
    INSTALL_COMMAND   ${STRIP_LIBS_COMMAND} && mkdir -p ${DST} && cp ${BINARIES} ${LIBRARIES} ${DST} && ${STRIP_DST_COMMAND}
    )
endif()

install(CODE "MESSAGE(\"Installed kaldi engine binaries.\")")
