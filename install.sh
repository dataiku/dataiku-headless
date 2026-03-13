#!/usr/bin/env bash
# Install dku-cli — Developer CLI for Dataiku DSS
# Usage: curl -fsSL https://raw.githubusercontent.com/christiaanburrett/dku-cli/main/install.sh | bash
set -euo pipefail

PACKAGE="dku-cli"
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

# Try installers in order of preference
if command -v uvx &>/dev/null; then
    echo -e "${DIM}Using uv...${RESET}"
    uv tool install "$PACKAGE"
elif command -v pipx &>/dev/null; then
    echo -e "${DIM}Using pipx...${RESET}"
    pipx install "$PACKAGE"
elif command -v pip &>/dev/null; then
    echo -e "${DIM}Using pip...${RESET}"
    pip install --user "$PACKAGE"
elif command -v pip3 &>/dev/null; then
    echo -e "${DIM}Using pip3...${RESET}"
    pip3 install --user "$PACKAGE"
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
