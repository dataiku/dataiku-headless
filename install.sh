#!/usr/bin/env bash
# Install dku-cli — Developer CLI for Dataiku DSS
# Usage: bash <(gh api repos/dataiku/dataiku-cli/contents/install.sh --jq '.content' | base64 -d)
# Public repos: curl -fsSL https://raw.githubusercontent.com/dataiku/dataiku-cli/main/install.sh | bash
set -euo pipefail

PACKAGE="dku-cli"
SOURCE="git+https://github.com/dataiku/dataiku-cli.git"
BOLD="\033[1m"
GREEN="\033[32m"
BLUE="\033[34m"
DIM="\033[2m"
RESET="\033[0m"

echo -e "${BLUE}"
cat << 'LOGO'
               ......       ...........                 ...               ...  ...
              .......       ...    ......               ...               ...  ...
            ........        ...       ....   ........ .......  ........   ...  ...   .... ..      ..
           .........        ...        ...  ...   ....  ...   ....  ....  ...  ... .....  ...     ..
         ...........        ...        ...  ..   .....  ...   ...   ....  ...  .......    ...     ..
        ...........         ...        ...  ..........  ...    .........  ...  ......     ...     ..
      ............          ...       ...  ....    ...  ...   ...    ...  ...  .......    ...    ...
    ...... ..........       ............   ....  .....  ..... ...  .....  ...  ...  ....  ..........
   ...     ..........       ..........      ....... ..   ....  ...... ..  ...  ...    ...  .........
 ...
..
LOGO
echo -e "${RESET}"
echo ""
echo -e "${DIM}  Installing ${PACKAGE}${RESET}"
echo ""

# Install from GitHub (not on PyPI)
if command -v uvx &>/dev/null; then
    echo -e "${DIM}Using uv...${RESET}"
    uv tool install "$SOURCE"
elif command -v pipx &>/dev/null; then
    echo -e "${DIM}Using pipx...${RESET}"
    pipx install "$SOURCE"
elif command -v pip &>/dev/null; then
    echo -e "${DIM}Using pip...${RESET}"
    pip install --user "$SOURCE"
elif command -v pip3 &>/dev/null; then
    echo -e "${DIM}Using pip3...${RESET}"
    pip3 install --user "$SOURCE"
else
    echo "Error: No Python package manager found."
    echo "Install uv (recommended): curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo ""

# Verify installation
if command -v dku &>/dev/null; then
    echo -e "${GREEN}$(dku --version)${RESET}"
    echo ""
    echo "Get started:"
    echo "  dku auth login     # Connect to your DSS instance"
    echo "  dku --help         # See all commands"
else
    echo -e "${GREEN}◆ Installed successfully${RESET}"
    echo ""
    echo "You may need to restart your shell or add ~/.local/bin to PATH."
    echo "Then run: dku auth login"
fi

echo ""
echo -e "${DIM}AI agent skills available:${RESET}"
echo "  npx skills add dataiku/dataiku-cli --all"
