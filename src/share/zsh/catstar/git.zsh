# Catstar Git & Development Utilities
# -----------------------------------------------------------------------------
# This file contains wrappers for managing Git repositories and development
# environments (pyenv, rbenv, etc.)
# -----------------------------------------------------------------------------

# --- Environment Manager Updates ---
# These functions use the autoloaded 'update_repo' function to pull changes
# for various version managers and tools.

# Update pyenv (Python version manager)
update_pyenv() { 
  update_repo "pyenv/pyenv" "$HOME/.pyenv" 
}

# Update rbenv and ruby-build (Ruby version manager)
update_rbenv() {
  update_repo "rbenv/rbenv" "$HOME/.rbenv"
  update_repo "rbenv/ruby-build" "$HOME/.rbenv/plugins/ruby-build"
}

# Update nodenv and node-build (Node.js version manager)
update_nodenv() {
  update_repo "nodenv/nodenv" "$HOME/.nodenv"
  update_repo "nodenv/node-build" "$HOME/.nodenv/plugins/node-build"
}

# --- Editor & Plugin Updates ---

# Update vim-plug (Vim plugin manager)
update_vim_plug() { 
  update_repo "junegunn/vim-plug" "$HOME/.vim/vim-plug" 
}

# Update Oh My Zsh
update_oh_my_zsh() { 
  update_repo "ohmyzsh/oh-my-zsh" "$HOME/.oh-my-zsh" 
}

# Update nvm (Node Version Manager)
update_nvm() { 
  update_repo "nvm-sh/nvm" "$HOME/.nvm" 
}
