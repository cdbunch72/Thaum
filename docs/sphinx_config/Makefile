# Minimal Sphinx Makefile (Unix).
# Usage (from anywhere):
#   make -C docs/sphinx_config html
#   make -C docs/sphinx_config help
#   make -C docs/sphinx_config clean
#
# Other builders (singlehtml, text, etc.) via sphinx-build -M <builder>.

SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = ..
BUILDDIR      = ../_build
CONFDIR       = .

.PHONY: help html clean

help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) -c "$(CONFDIR)"

html:
	@$(SPHINXBUILD) -M html "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) -c "$(CONFDIR)"

clean:
	@$(SPHINXBUILD) -M clean "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) -c "$(CONFDIR)"
