# Catstar Git & Development Utilities
# -----------------------------------------------------------------------------
# This file contains wrappers for managing Git repositories and development
# environments (pyenv, rbenv, etc.)
# -----------------------------------------------------------------------------

# --- Environment Manager Updates ---
# These functions use the autoloaded 'git-update-repo' function to pull changes
# for various version managers and tools.

# Update pyenv (Python version manager)
update_pyenv() {
  git-update-repo "pyenv/pyenv" "$HOME/.pyenv"
}

# Update rbenv and ruby-build (Ruby version manager)
update_rbenv() {
  git-update-repo "rbenv/rbenv" "$HOME/.rbenv"
  git-update-repo "rbenv/ruby-build" "$HOME/.rbenv/plugins/ruby-build"
}

# Update nodenv and node-build (Node.js version manager)
update_nodenv() {
  git-update-repo "nodenv/nodenv" "$HOME/.nodenv"
  git-update-repo "nodenv/node-build" "$HOME/.nodenv/plugins/node-build"
}

# --- Editor & Plugin Updates ---

# Update vim-plug (Vim plugin manager)
update_vim_plug() {
  git-update-repo "junegunn/vim-plug" "$HOME/.vim/vim-plug"
}

# Update Oh My Zsh
update_oh_my_zsh() {
  git-update-repo "ohmyzsh/oh-my-zsh" "$HOME/.oh-my-zsh"
}

# Update nvm (Node Version Manager)
update_nvm() {
  git-update-repo "nvm-sh/nvm" "$HOME/.nvm"
}
