cmake_minimum_required(VERSION 3.14)
project(dnn_wrapper)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(FetchContent)

# — pybind11 via GitHub —  
FetchContent_Declare(
  pybind11
  GIT_REPOSITORY https://github.com/pybind/pybind11.git
  GIT_TAG        v2.11.1
)
FetchContent_MakeAvailable(pybind11)

# — DLib via GitHub —
FetchContent_Declare(
  dlib
  GIT_REPOSITORY https://github.com/davisking/dlib.git
  GIT_TAG        v19.24   # or latest
)
FetchContent_MakeAvailable(dlib)

# Build the Python extension
pybind11_add_module(dnn_wrapper
  dnn_wrapper.cpp
)

# Link it to the DLib target
target_link_libraries(dnn_wrapper PRIVATE dlib::dlib)

# Place the .pyd/.dll next to your Flask server.py
set_target_properties(dnn_wrapper PROPERTIES
  LIBRARY_OUTPUT_DIRECTORY ${CMAKE_SOURCE_DIR}/..
)
