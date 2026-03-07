# Git repository management wrappers
# Managed by autoloaded functions

update_pyenv() { update_repo pyenv/pyenv ~/.pyenv }
update_rbenv() {
    update_repo rbenv/rbenv ~/.rbenv
    update_repo rbenv/ruby-build ~/.rbenv/plugins/ruby-build
}
update_nodenv() {
    update_repo nodenv/nodenv ~/.nodenv
    update_repo nodenv/node-build ~/.nodenv/plugins/node-build
}
update_vim_plug() { update_repo junegunn/vim-plug ~/.vim/vim-plug }
update_oh_my_zsh() { update_repo ohmyzsh/oh-my-zsh ~/.oh-my-zsh }
update_nvm() { update_repo nvm-sh/nvm ~/.nvm }

gtr() { gtoggle_remote "$@" }
