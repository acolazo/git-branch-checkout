#!/usr/bin/python3

import curses
import time
from shutil import which
import subprocess
from functools import partial

GIT_CMD = 'git'
DEFAULT_TIMEOUT = 10.0

def run_command(cmd, timeout=DEFAULT_TIMEOUT):
    """Run a command"""
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        msg = f"A timeout occured while running the command: {cmd}"
        raise RuntimeError(msg)

    if proc.returncode == 0:
        return out.strip()
    else:
        return err.strip()

class Git:
    """Helper class to run Git commands"""

    def __init__(self, git_cmd=GIT_CMD):
        self.git_cmd = git_cmd

    def exists(self):
        """Check if the git command exists"""
        return which(self.git_cmd) is not None

    def is_inside_work_tree(self):
        """Check if we are inside a git repository"""
        command = [self.git_cmd, 'rev-parse', '--is-inside-work-tree']
        out = run_command(command)
        return out.strip() == 'true'

    def switch(self, branch):
        """Switch to a branch"""
        command = [self.git_cmd, 'switch', branch]
        return run_command(command)

    def delete_local_branch(self, branch):
        """Delete a local branch"""
        command = [self.git_cmd, 'branch', '--delete', branch]
        run_command(command)

    def get_branches(self, remote=False):
        """Get local or remote branches"""
        command = [self.git_cmd, 'branch']
        if remote:
            command.append("--remote")
        branches = run_command(command).split("\n")
        branches = [branch.strip() for branch in branches]
        try:
            branches.remove('*')
        except ValueError:
            pass
        return branches

    def fetch(self):
        """Fetch remote branches."""
        command = [self.git_cmd, 'fetch']
        run_command(command)

    def get_current_branch(self):
        """Get current branch"""
        command = [self.git_cmd, 'rev-parse', '--abbrev-ref', 'HEAD']
        return run_command(command)

class MenuApp:
    def __init__(self, stdscr, git: Git) -> None:
        self.git = git
        self.show_remote: bool = False
        self.confirm_delete_branch: bool = False
        self.confirm_choice = False
        self.branches = self.git.get_branches()
        self.remote_branches = self.git.get_branches(remote=True)
        self.current_branch = self.git.get_current_branch()
        self.selected: int = 0
        self.top: int = 0
        self.stdscr = stdscr

    @property
    def items(self):
        """
        Returns current menu items, either local branches or remote branches.
        """
        return self.remote_branches if self.show_remote else self.branches

    def draw(self) -> tuple[int, int]:
        """
        Draw the UI and return (selected, top) clamped to the current viewport.
        """
        # Use default terminal background by clearing with erase()
        self.stdscr.erase()

        h, w = self.stdscr.getmaxyx()

        # Left menu width
        menu_w = max(20, min(36, w // 3))
        sep_x = menu_w + 1
        content_x = sep_x + 2

        # Header
        header = "Menu (↑/↓) | R = action | q = quit"
        self.stdscr.addstr(0, 2, header[: max(0, w - 4)], curses.A_BOLD)

        # Determine menu viewport
        menu_y0 = 2
        menu_y1 = h - 3
        view_h = max(1, menu_y1 - menu_y0 + 1)

        n = len(self.items)
        if n == 0:
            self.items = ["(empty)"]
            n = 1
            self.selected = 0
            self.top = 0

        # Clamp selected
        self.selected = max(0, min(self.selected, n - 1))

        # Keep selected visible; clamp top
        if self.selected < self.top:
            self.top = self.selected
        elif self.selected >= self.top + view_h:
            self.top = self.selected - view_h + 1
        self.top = max(0, min(self.top, max(0, n - view_h)))

        # Separator
        if sep_x < w:
            for y in range(1, h):
                self.stdscr.addch(y, sep_x, "│")

        # Scroll indicators
        if self.top > 0 and menu_y0 - 1 >= 1:
            self.stdscr.addstr(menu_y0 - 1, 2, "↑ more")
        if self.top + view_h < n and menu_y1 + 1 < h - 1:
            self.stdscr.addstr(menu_y1 + 1, 2, "↓ more")

        # Menu render (left)
        for i in range(view_h):
            idx = self.top + i
            if idx >= n:
                break
            y = menu_y0 + i

            label = self.items[idx][: max(0, menu_w - 4)]
            line = ("> " if idx == self.selected else "  ") + label
            line = line.ljust(max(0, menu_w - 1))

            if idx == self.selected:
                self.stdscr.addstr(y, 2, line[: max(0, w - 3)], curses.A_REVERSE)
            else:
                self.stdscr.addstr(y, 2, line[: max(0, w - 3)])

        # Content (right)
        if not self.confirm_delete_branch:
            self.draw_current_selection_and_commands(content_x, h, w)
        else:
            self.draw_confirm_menu(content_x, h, w)

        # Status line
        if h - 2 >= 0:
            self.stdscr.addstr(h - 2, 2, " " * max(0, w - 4))
            self.stdscr.addstr(h - 2, 2, "Ready"[: max(0, w - 4)], curses.A_DIM)

        self.stdscr.refresh()
        return self.selected, self.top

    def draw_current_selection_and_commands(self, x0: int, h: int, w: int) -> None:
        """
        Draw current selection, current branch and available commands.
        """
        sel_item = self.get_selected_branch()
        content_lines = [
            f"Curent branch: {self.current_branch}",
            "",
            f"Selected: {sel_item}",
            "",
            "Press ENTER to switch to a branch.",
            "Press `r` to toggle remote branches on/off.",
            "Press `f` to fetch branches.",
            "Press `d` to delete a local branch.",
            "Press `q` to quit.",
        ]
        cy = 2
        for line in content_lines:
            if cy >= h - 2:
                break
            if x0 < w - 1:
                attr = curses.A_DIM if line == "Content" else 0
                self.stdscr.addstr(cy, x0, line[: (w - x0 - 1)], attr)
            cy += 1

    def draw_confirm_menu(self, x0: int, h: int, w: int) -> None:
        """
        Draw confirmation menu to delete a branch.
        """
        s = self.stdscr
        selected_branch = self.get_selected_branch()
        title = f"Delete branch `{selected_branch}`?"
        y = 3

        if x0 < w - 1:
            s.addstr(y, x0, title[: (w - x0 - 1)], curses.A_BOLD)
        y += 2

        # Horizontal choices: Yes / No
        yes = " Yes "
        no = " No  "

        # Render with highlight on current choice
        # confirm_choice: 0=Yes, 1=No
        yes_attr = curses.A_REVERSE if self.confirm_choice else 0
        no_attr = curses.A_REVERSE if not self.confirm_choice else 0

        if x0 < w - 1 and y < h - 2:
            s.addstr(y, x0, yes, yes_attr)
            s.addstr(y, x0 + len(yes) + 1, no, no_attr)

        # Help text
        y += 2
        help_lines = [
            "Use ←/→ to choose.",
            "Enter = confirm, Esc = cancel.",
        ]
        for line in help_lines:
            if y >= h - 2:
                break
            if x0 < w - 1:
                s.addstr(y, x0, line[: (w - x0 - 1)], curses.A_DIM)
            y += 1


    def toggle_remote_branches(self) -> None:
        """
        Toggle remote branches on/off.
        """
        self.show_remote = not self.show_remote
        status = "on" if self.show_remote else "off"
        self.draw()
        msg = f"Show remote branches: {status}"
        self.temporal_message(msg)

    def open_delete_local_branch(self) -> None:
        """
        Open confirmation menu to delete local branch.
        """
        if self.show_remote:
            self.temporal_message("Cannot delete remote branch")
            return
        selected_branch = self.get_selected_branch()
        if selected_branch == self.current_branch:
            self.temporal_message(f"Cannot delete checked out branch: {selected_branch}")
            return
        self.confirm_choice = False
        self.confirm_delete_branch = True
    
    def close_delete_local_branch(self) -> None:
        """
        Close confirmation menu to delete local branch.
        """
        self.confirm_choice = False
        self.confirm_delete_branch = False

    def delete_local_branch(self) -> None:
        """
        Delete a local git branch.
        """
        self.close_delete_local_branch()
        selected_branch = self.get_selected_branch()
        self.git.delete_local_branch(selected_branch)
        self.branches = self.git.get_branches()
        self.draw()
        msg = f"Delete local branch: {selected_branch}"
        self.temporal_message(msg)

    def git_switch_to_branch(self):
        """
        Call git switch to a branch.
        """
        branch = self.get_selected_branch()
        if self.show_remote:
            branch = branch.strip("origin/")
        msg = self.git.switch(branch)
        self.current_branch = self.git.get_current_branch()
        self.branches = self.git.get_branches()
        self.show_remote = False
        self.draw()
        self.temporal_message(msg)

    def git_fetch(self):
        """
        Call git fetch.
        """
        self.git.fetch()
        self.remote_branches = self.git.get_branches(remote=True)
        self.draw()
        self.temporal_message("Fetched branches")

    def get_selected_branch(self):
        """
        Returns name of selected branch.
        """
        selected_branch = self.items[self.selected]
        if selected_branch == f"* {self.current_branch}":
            return self.current_branch
        else:
            return selected_branch

    def temporal_message(self, msg: str):
        """
        Show temporal message at the bottom.
        """
        h, w = self.stdscr.getmaxyx()
        lines = msg.count("\n")
        h = max(h - lines, 2)
        self.stdscr.addstr(h - 2, 2, " " * max(0, w - 4))
        self.stdscr.addstr(h - 2, 2, msg[: max(0, w - 4)])
        self.stdscr.refresh()
        time.sleep(0.5)

    def handle_key(self, ch: int) -> bool:
        """
        Handle one keypress. Return False to quit, True to continue.
        """
        if self.confirm_delete_branch:
            if ch in (curses.KEY_ENTER, 10, 13, ord("q"), ord("Q")):
                if self.confirm_choice:
                    self.delete_local_branch()
                else:
                    self.close_delete_local_branch()
                return True

            if ch in (27, ord("q"), ord("Q")):
                self.close_delete_local_branch()
                return True

            if ch == curses.KEY_RIGHT:
                self.confirm_choice = False
                return True

            if ch == curses.KEY_LEFT:
                self.confirm_choice = True
                return True

        else:
            if ch in (27, ord("q"), ord("Q")):
                return False

            if ch == curses.KEY_UP:
                self.selected = max(0, self.selected - 1)
                return True

            if ch == curses.KEY_DOWN:
                self.selected = min(len(self.items) - 1, self.selected + 1)
                return True

            if ch == ord("r"):
                self.toggle_remote_branches()
                return True

            if ch == ord("d"):
                self.open_delete_local_branch()
                return True

            if ch == ord("f"):
                self.git_fetch()
                return True

            if ch in (curses.KEY_ENTER, 10, 13):
                self.git_switch_to_branch()
                return True

        return True

    def run(self) -> None:
        curses.curs_set(0)
        self.stdscr.keypad(True)

        # Keep terminal default background/colors
        curses.start_color()
        curses.use_default_colors()

        while True:
            self.draw()
            ch = self.stdscr.getch()
            if not self.handle_key(ch):
                break


def app(stdscr, git) -> None:
    MenuApp(stdscr, git).run()

if __name__ == "__main__":
    git = Git()
    if not git.exists():
        print(f'{git.git_cmd} command was not found')
        exit(1)
    if not git.is_inside_work_tree():
        print('Not inside a git repository')
        exit(1)
    curses.wrapper(partial(app, git=git))
