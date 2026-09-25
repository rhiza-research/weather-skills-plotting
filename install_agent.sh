#!/usr/bin/env bash
# Install the plotting agent and skills as a Claude Code plugin.
set -e

claude plugin marketplace add rhiza-research/weather-skills-plotting
claude plugin install rhiza-plotting@weather-skills-plotting

cat <<'EOF'

Installed the rhiza-plotting plugin.

Next steps:

# Then run the agent
claude --agent rhiza-plotting:plotting

EOF
