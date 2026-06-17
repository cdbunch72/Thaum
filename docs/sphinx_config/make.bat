@REM Sphinx build helper (Windows).
@REM Usage:
@REM   docs\sphinx_config\make.bat html
@REM   docs\sphinx_config\make.bat help
@REM   docs\sphinx_config\make.bat clean
@REM
@REM Other builders: sphinx-build -M singlehtml|text -c docs\sphinx_config docs docs\_build

@echo off
setlocal

pushd "%~dp0"

set SPHINXBUILD=sphinx-build
set SOURCEDIR=..
set BUILDDIR=../_build
set CONFDIR=.

if "%1"=="" goto help

%SPHINXBUILD% -M %1 %SOURCEDIR% %BUILDDIR% -c %CONFDIR% %SPHINXOPTS% %O%
goto end

:help
%SPHINXBUILD% -M help %SOURCEDIR% %BUILDDIR% -c %CONFDIR% %SPHINXOPTS% %O%

:end
popd
endlocal
