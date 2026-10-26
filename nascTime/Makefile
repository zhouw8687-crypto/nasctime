.PHONY: all clean cleanall makefiles checkenvir tests

all: makefiles
	@cd src && $(MAKE)

tests: all
	@cd tests/fingerprint && ./fingerprints

clean: makefiles
	@cd src && $(MAKE) clean

cleanall: makefiles
	@cd src && $(MAKE) MODE=release clean
	@cd src && $(MAKE) MODE=debug clean
	@rm -f src/Makefile

# nascTime imports both INET and Simu5G. Their locations come from the
# INET_ROOT / SIMU5G_ROOT environment variables (exported by sourcing each
# project's own 'setenv'), exactly as Simu5G consumes INET_ROOT. There is no
# hardcoded sibling-directory default; override on the command line if needed:
#   make INET_ROOT=/path/to/inet SIMU5G_ROOT=/path/to/simu5g
checkenvir:
	@if [ -z "$(INET_ROOT)" ] || [ ! -d "$(INET_ROOT)/src" ]; then \
	echo; \
	echo '======================================================================='; \
	echo 'INET_ROOT is not set, or does not point to an INET tree.'; \
	echo 'Source INET'\''s setenv before building, or pass INET_ROOT=<path>.'; \
	echo '======================================================================='; \
	echo; \
	exit 1; \
	fi
	@if [ -z "$(SIMU5G_ROOT)" ] || [ ! -d "$(SIMU5G_ROOT)/src" ]; then \
	echo; \
	echo '======================================================================='; \
	echo 'SIMU5G_ROOT is not set, or does not point to a Simu5G tree.'; \
	echo 'Source Simu5G'\''s setenv before building, or pass SIMU5G_ROOT=<path>.'; \
	echo '======================================================================='; \
	echo; \
	exit 1; \
	fi

# Extract the makemake options from .oppbuildspec so the command-line build and
# the IDE build stay in sync (single source of truth). The IDE writes --meta:xxx
# options that opp_makemake does not accept on the command line, so translate
# --meta:export-include-path to -I. , add -f before --deep, and drop the rest.
MAKEMAKE_OPTIONS := $(shell sed -n 's/.*makemake-options\s*=\s*"\([^"]*\)".*/\1/p' .oppbuildspec | sed 's/--meta:export-include-path/-I./g' | sed 's/--deep/-f --deep/g' | sed 's/ --meta:[^ ]*//g')
# Add the options that pull in the INET and Simu5G dependencies.
MAKEMAKE_OPTIONS := $(MAKEMAKE_OPTIONS) -KINET_PROJ=$(INET_ROOT) -KSIMU5G_PROJ=$(SIMU5G_ROOT) -DINET_IMPORT -DSIMU5G_IMPORT -I. -I$$\(INET_PROJ\)/src -I$$\(SIMU5G_PROJ\)/src -L$$\(INET_PROJ\)/src -L$$\(SIMU5G_PROJ\)/src -lINET$$\(D\) -lsimu5g$$\(D\)

makefiles: checkenvir
	@$(info *** CREATING Makefile with:)
	@$(info opp_makemake $(MAKEMAKE_OPTIONS))
	@cd src && opp_makemake $(MAKEMAKE_OPTIONS)
