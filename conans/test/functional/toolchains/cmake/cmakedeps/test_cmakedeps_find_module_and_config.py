import textwrap

import pytest

from conans.test.assets.cmake import gen_cmakelists
from conans.test.assets.genconanfile import GenConanfile
from conans.test.assets.sources import gen_function_cpp, gen_function_h
from conans.test.utils.tools import TestClient


@pytest.fixture(scope="module")
def client():
    t = TestClient()
    cpp = gen_function_cpp(name="mydep")
    h = gen_function_h(name="mydep")
    cmake = gen_cmakelists(libname="mydep", libsources=["mydep.cpp"])
    conanfile = textwrap.dedent("""
        import os
        from conans import ConanFile
        from conan.tools.cmake import CMake

        class Conan(ConanFile):
            name = "mydep"
            version = "1.0"
            settings = "os", "arch", "compiler", "build_type"
            exports_sources = "*.cpp", "*.h", "CMakeLists.txt"
            generators = "CMakeToolchain"

            def build(self):
                cmake = CMake(self)
                cmake.configure()
                cmake.build()

            def package(self):
                self.copy("*.h", dst="include")
                self.copy("*.lib", dst="lib", keep_path=False)
                self.copy("*.dll", dst="bin", keep_path=False)
                self.copy("*.dylib*", dst="lib", keep_path=False)
                self.copy("*.so", dst="lib", keep_path=False)
                self.copy("*.a", dst="lib", keep_path=False)

            def package_info(self):

                self.cpp_info.set_property("cmake_find_mode", "both")

                self.cpp_info.set_property("cmake_file_name", "MyDep")
                self.cpp_info.set_property("cmake_target_name", "MyDepTarget::MyDepTarget")

                self.cpp_info.set_property("cmake_module_file_name", "mi_dependencia")
                self.cpp_info.set_property("cmake_module_target_name", "mi_dependencia_namespace::mi_dependencia_target")

                self.cpp_info.components["crispin"].libs = ["mydep"]
                self.cpp_info.components["crispin"].set_property("cmake_target_name",
                                                                 "MyDepTarget::MyCrispinTarget")
                self.cpp_info.components["crispin"].set_property("cmake_module_target_name",
                                                                 "mi_dependencia_namespace::mi_crispin_target")
        """)

    t.save({"conanfile.py": conanfile,
            "mydep.cpp": cpp,
            "mydep.h": h,
            "CMakeLists.txt": cmake})

    t.run("create .")
    return t


@pytest.mark.tool_cmake
def test_reuse_with_modules_and_config(client):
    cpp = gen_function_cpp(name="main")

    cmake_exe_config = """
    add_executable(myapp main.cpp)
    find_package(MyDep) # This one will find the config
    target_link_libraries(myapp MyDepTarget::MyCrispinTarget)
    """

    cmake_exe_module = """
    add_executable(myapp2 main.cpp)
    find_package(mi_dependencia) # This one will find the module
    target_link_libraries(myapp2 mi_dependencia_namespace::mi_crispin_target)
    """

    cmake = """
    set(CMAKE_CXX_COMPILER_WORKS 1)
    set(CMAKE_CXX_ABI_COMPILED 1)
    set(CMAKE_C_COMPILER_WORKS 1)
    set(CMAKE_C_ABI_COMPILED 1)

    cmake_minimum_required(VERSION 3.15)
    project(project CXX)
    {}
    """

    # test config
    conanfile = GenConanfile().with_name("myapp")\
        .with_cmake_build().with_exports_sources("*.cpp", "*.txt").with_require("mydep/1.0")
    client.save({"conanfile.py": conanfile,
                 "main.cpp": cpp,
                 "CMakeLists.txt": cmake.format(cmake_exe_config)})

    client.run("install . -if=install")
    client.run("build . -if=install")

    # test modules
    conanfile = GenConanfile().with_name("myapp")\
        .with_cmake_build().with_exports_sources("*.cpp", "*.txt").with_require("mydep/1.0")
    client.save({"conanfile.py": conanfile,
                 "main.cpp": cpp,
                 "CMakeLists.txt": cmake.format(cmake_exe_module)}, clean_first=True)

    client.run("install . -if=install")
    client.run("build . -if=install")


find_modes = [
    ("both", "both", ""),
    ("config", "config", ""),
    ("module", "module", ""),
    ("both", None, ""),
    ("both", None, "MODULE")
]


@pytest.mark.parametrize("find_mode_PKGA, find_mode_PKGB, find_mode_consumer", find_modes)
def test_transitive_modules_found(find_mode_PKGA, find_mode_PKGB, find_mode_consumer):
    """
    related to https://github.com/conan-io/conan/issues/10224
    modules files variables were set with the pkg_name_FOUND or pkg_name_VERSION
    instead of using filename_*, also there was missing doing a find_dependency of the
    requires packages to find_package transitive dependencies
    """
    client = TestClient()
    conan_pkg = textwrap.dedent("""
        from conan import ConanFile
        class Pkg(ConanFile):
            {requires}
            def package_info(self):
                if "{mode}" != "None":
                    self.cpp_info.set_property("cmake_find_mode", "{mode}")
                self.cpp_info.set_property("cmake_file_name", "{filename}")
                self.cpp_info.defines.append("DEFINE_{filename}")
            """)

    consumer = textwrap.dedent("""
        from conan import ConanFile
        from conan.tools.cmake import CMake
        class Consumer(ConanFile):
            settings = "os", "compiler", "arch", "build_type"
            requires = "pkgb/1.0"
            generators = "CMakeDeps", "CMakeToolchain"
            exports_sources = "CMakeLists.txt"
            def build(self):
                cmake = CMake(self)
                cmake.configure()
                cmake.build()
        """)

    cmakelist = textwrap.dedent("""
        cmake_minimum_required(VERSION 3.1)
        project(test_package CXX)
        find_package(MYPKGB REQUIRED {find_mode})
        message("MYPKGB_VERSION: ${{MYPKGB_VERSION}}")
        message("MYPKGB_VERSION_STRING: ${{MYPKGB_VERSION_STRING}}")
        message("MYPKGB_INCLUDE_DIRS: ${{MYPKGB_INCLUDE_DIRS}}")
        message("MYPKGB_INCLUDE_DIR: ${{MYPKGB_INCLUDE_DIR}}")
        message("MYPKGB_LIBRARIES: ${{MYPKGB_LIBRARIES}}")
        message("MYPKGB_DEFINITIONS: ${{MYPKGB_DEFINITIONS}}")
        """)

    client.save({"pkgb.py": conan_pkg.format(requires='requires="pkga/1.0"', filename='MYPKGB',
                                             mode=find_mode_PKGA),
                 "pkga.py": conan_pkg.format(requires='', filename='MYPKGA', mode=find_mode_PKGB),
                 "consumer.py": consumer,
                 "CMakeLists.txt": cmakelist.format(find_mode=find_mode_consumer)})
    client.run("create pkga.py pkga/1.0@")
    client.run("create pkgb.py pkgb/1.0@")
    client.run("create consumer.py consumer/1.0@")

    assert "MYPKGB_VERSION: 1.0" in client.out
    assert "MYPKGB_VERSION_STRING: 1.0" in client.out
    assert "MYPKGB_INCLUDE_DIRS:" in client.out
    assert "MYPKGB_INCLUDE_DIR:" in client.out
    assert "MYPKGB_LIBRARIES: pkga::pkga" in client.out
    assert "MYPKGB_DEFINITIONS: -DDEFINE_MYPKGB" in client.out
    assert "Conan: Target declared 'pkga::pkga'"
    if find_mode_PKGA == "module":
        assert 'Found MYPKGA: 1.0 (found version "1.0")' in client.out
