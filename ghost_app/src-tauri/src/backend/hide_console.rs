//! Hide the console window for child processes on Windows (avoids flashing cmd.exe during deploy).

use tokio::process::Command;

/// Sets `CREATE_NO_WINDOW` on Windows; no-op on other platforms.
pub fn hide_child_console(cmd: &mut Command) {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        cmd.as_std_mut().creation_flags(0x0800_0000);
    }
}
