# Oh My Zsh Git Plugin Cheatsheet

This cheatsheet documents the aliases provided by the Oh My Zsh `git` plugin.

## General
| Alias | Command | Description |
| :--- | :--- | :--- |
| `g` | `git` | The entry point for all git commands |
| `grt` | `cd "$(git rev-parse --show-toplevel \|\| echo .)"` | Change directory to the git repository root |

## Add
| Alias | Command | Description |
| :--- | :--- | :--- |
| `ga` | `git add` | Add file contents to the index |
| `gaa` | `git add --all` | Add all changes to the index |
| `gapa` | `git add --patch` | Interactively choose hunks of patch between the index and the work tree |
| `gau` | `git add --update` | Update the index just where it already has an entry matching <pathspec> |
| `gav` | `git add --verbose` | Be verbose |
| `gwip` | `git add -A; git commit --message "--wip--"` | Commit as Work In Progress |

## Apply
| Alias | Command | Description |
| :--- | :--- | :--- |
| `gap` | `git apply` | Apply a patch to files and/or to the index |
| `gapt` | `git apply --3way` | Attempt 3-way merge if a patch does not apply cleanly |

## Branch
| Alias | Command | Description |
| :--- | :--- | :--- |
| `gb` | `git branch` | List, create, or delete branches |
| `gba` | `git branch --all` | List both remote-tracking branches and local branches |
| `gbd` | `git branch --delete` | Delete a branch |
| `gbD` | `git branch --delete --force` | Delete a branch irrespective of its merged status |
| `gbm` | `git branch --move` | Move/rename a branch |
| `gbnm` | `git branch --no-merged` | List branches which have not been merged |
| `gbr` | `git branch --remote` | List or delete (if used with -d) the remote-tracking branches |
| `ggsup` | `git branch --set-upstream-to=origin/$(git_current_branch)` | Set upstream branch for the current branch |
| `gbg` | `LANG=C git branch -vv \| grep ": gone]"` | List branches whose upstream is gone |
| `gbgd` | `... \| xargs git branch -d` | Delete local branches whose upstream is gone |
| `gbgD` | `... \| xargs git branch -D` | Force delete local branches whose upstream is gone |

## Checkout
| Alias | Command | Description |
| :--- | :--- | :--- |
| `gco` | `git checkout` | Switch branches or restore working tree files |
| `gcor` | `git checkout --recurse-submodules` | Checkout and update submodules |
| `gcb` | `git checkout -b` | Create and switch to a new branch |
| `gcB` | `git checkout -B` | Create or reset and switch to a new branch |
| `gcd` | `git checkout $(git_develop_branch)` | Checkout the development branch |
| `gcm` | `git checkout $(git_main_branch)` | Checkout the main branch |

## Cherry-pick
| Alias | Command | Description |
| :--- | :--- | :--- |
| `gcp` | `git cherry-pick` | Apply the changes introduced by some existing commits |
| `gcpa` | `git cherry-pick --abort` | Cancel the cherry-pick operation |
| `gcpc` | `git cherry-pick --continue` | Continue the cherry-pick operation |

## Clean
| Alias | Command | Description |
| :--- | :--- | :--- |
| `gclean` | `git clean --interactive -d` | Remove untracked files from the working tree interactively |

## Clone
| Alias | Command | Description |
| :--- | :--- | :--- |
| `gcl` | `git clone --recurse-submodules` | Clone a repository including submodules |
| `gclf` | `git clone --recursive --shallow-submodules ...` | Clone a repository with shallow submodules |

## Commit
| Alias | Command | Description |
| :--- | :--- | :--- |
| `gc` | `git commit --verbose` | Record changes to the repository |
| `gca` | `git commit --verbose --all` | Commit all changed files |
| `gca!` | `git commit --verbose --all --amend` | Amend the last commit including all changes |
| `gcan!` | `git commit --verbose --all --no-edit --amend` | Amend the last commit with all changes, without changing message |
| `gcmsg` | `git commit --message` | Commit with a message |
| `gcam` | `git commit --all --message` | Commit all files with a message |
| `gc!` | `git commit --verbose --amend` | Amend the last commit |
| `gcn!` | `git commit --verbose --no-edit --amend` | Amend the last commit without changing message |
| `gcfu` | `git commit --fixup` | Create a fixup commit for use with rebase --autosquash |

## Diff
| Alias | Command | Description |
| :--- | :--- | :--- |
| `gd` | `git diff` | Show changes between commits, commit and working tree, etc |
| `gdca` | `git diff --cached` | Show changes between index and last commit |
| `gds` | `git diff --staged` | Show changes between staged changes and last commit |
| `gdw` | `git diff --word-diff` | Show word diff |
| `gdup` | `git diff @{upstream}` | Show diff with upstream branch |

## Fetch
| Alias | Command | Description |
| :--- | :--- | :--- |
| `gf` | `git fetch` | Download objects and refs from another repository |
| `gfa` | `git fetch --all --tags --prune --jobs=10` | Fetch all remotes, tags, and prune deleted branches |
| `gfo` | `git fetch origin` | Fetch from origin |

## Log
| Alias | Command | Description |
| :--- | :--- | :--- |
| `glol` | `git log --graph --pretty="..."` | Visual log with relative dates |
| `glola` | `git log --graph --pretty="..." --all` | Visual log for all branches |
| `glog` | `git log --oneline --decorate --graph` | Oneline log with graph |
| `gloga` | `git log --oneline --decorate --graph --all` | Oneline log for all branches |
| `glo` | `git log --oneline --decorate` | Simple oneline log |
| `glg` | `git log --stat` | Log with stats |
| `glgp` | `git log --stat --patch` | Log with stats and patch |

## Merge
| Alias | Command | Description |
| :--- | :--- | :--- |
| `gm` | `git merge` | Join two or more development histories together |
| `gma` | `git merge --abort` | Abort the merge |
| `gmc` | `git merge --continue` | Continue the merge |
| `gms` | `git merge --squash` | Squash changes into a single commit |
| `gmff` | `git merge --ff-only` | Merge only if it can be a fast-forward |
| `gmom` | `git merge origin/$(git_main_branch)` | Merge main branch from origin |

## Pull
| Alias | Command | Description |
| :--- | :--- | :--- |
| `gl` | `git pull` | Fetch from and integrate with another repository or a local branch |
| `gpr` | `git pull --rebase` | Pull and rebase |
| `gpra` | `git pull --rebase --autostash` | Pull, rebase, and autostash |
| `ggl` | `git pull origin $(git_current_branch)` | Pull from origin for the current branch |
| `glum` | `git pull upstream $(git_main_branch)` | Pull main branch from upstream |

## Push
| Alias | Command | Description |
| :--- | :--- | :--- |
| `gp` | `git push` | Update remote refs along with associated objects |
| `gpd` | `git push --dry-run` | Dry run push |
| `gpf!` | `git push --force` | Force push |
| `gpf` | `git push --force-with-lease` | Safe force push |
| `gpsup` | `git push --set-upstream origin $(git_current_branch)` | Push and set upstream |
| `ggpush` | `git push origin $(git_current_branch)` | Push to origin for current branch |

## Rebase
| Alias | Command | Description |
| :--- | :--- | :--- |
| `grb` | `git rebase` | Reapply commits on top of another base tip |
| `grba` | `git rebase --abort` | Abort rebase |
| `grbc` | `git rebase --continue` | Continue rebase |
| `grbi` | `git rebase --interactive` | Interactive rebase |
| `grbs` | `git rebase --skip` | Skip current patch |
| `grbm` | `git rebase $(git_main_branch)` | Rebase onto main branch |

## Remote
| Alias | Command | Description |
| :--- | :--- | :--- |
| `gr` | `git remote` | Manage set of tracked repositories |
| `grv` | `git remote --verbose` | List remotes with URLs |
| `gra` | `git remote add` | Add a new remote |
| `grrm` | `git remote remove` | Remove a remote |
| `grup` | `git remote update` | Update remotes |

## Reset
| Alias | Command | Description |
| :--- | :--- | :--- |
| `grh` | `git reset` | Reset current HEAD to the specified state |
| `grhh` | `git reset --hard` | Hard reset (destroys changes) |
| `grhs` | `git reset --soft` | Soft reset (keeps changes staged) |
| `gpristine` | `git reset --hard && git clean --force -dfx` | Reset and clean EVERYTHING |

## Restore
| Alias | Command | Description |
| :--- | :--- | :--- |
| `grs` | `git restore` | Restore working tree files |
| `grst` | `git restore --staged` | Unstage files |

## Revert
| Alias | Command | Description |
| :--- | :--- | :--- |
| `grev` | `git revert` | Revert some existing commits |
| `greva` | `git revert --abort` | Abort revert |
| `grevc` | `git revert --continue` | Continue revert |

## Stash
| Alias | Command | Description |
| :--- | :--- | :--- |
| `gsta` | `git stash push` | Stash changes |
| `gstaa` | `git stash apply` | Apply stash |
| `gstl` | `git stash list` | List stashes |
| `gstp` | `git stash pop` | Pop stash |
| `gstd` | `git stash drop` | Drop stash |
| `gstu` | `git stash push --include-untracked` | Stash with untracked files |

## Status
| Alias | Command | Description |
| :--- | :--- | :--- |
| `gst` | `git status` | Show the working tree status |
| `gss` | `git status --short` | Show status in short format |
| `gsb` | `git status --short --branch` | Show status in short format with branch info |

## Submodule
| Alias | Command | Description |
| :--- | :--- | :--- |
| `gsi` | `git submodule init` | Initialize submodules |
| `gsu` | `git submodule update` | Update submodules |

## Switch
| Alias | Command | Description |
| :--- | :--- | :--- |
| `gsw` | `git switch` | Switch branches |
| `gswc` | `git switch --create` | Create and switch to a new branch |
| `gswm` | `git switch $(git_main_branch)` | Switch to the main branch |

## Tag
| Alias | Command | Description |
| :--- | :--- | :--- |
| `gta` | `git tag --annotate` | Create an annotated tag |
| `gtv` | `git tag \| sort -V` | List tags sorted by version |

## Worktree
| Alias | Command | Description |
| :--- | :--- | :--- |
| `gwt` | `git worktree` | Manage multiple working trees |
| `gwta` | `git worktree add` | Add a new worktree |
| `gwtls` | `git worktree list` | List worktrees |
| `gwtrm` | `git worktree remove` | Remove a worktree |
