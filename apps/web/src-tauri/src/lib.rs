// Tauri 2 entry for the desktop app. Unlike a pure web wrapper, this shell launches the bundled
// Python backend ("aec-bim-server" sidecar) — the same single-process runtime as the free .exe:
// FastAPI + the SPA + SQLite on 127.0.0.1, local mode. Once it's listening we point the WebView at
// it, so the whole app (API + UI) is same-origin and works fully offline. In `tauri dev` (no
// bundled sidecar) the spawn is skipped and the devUrl frontend loads as before.
use tauri::Manager;
use tauri_plugin_shell::ShellExt;

const PORT: u16 = 8765;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())   // native Open/Save dialogs
        .plugin(tauri_plugin_fs::init())        // read/write the chosen file
        .setup(|app| {
            // data dir under the OS app-data location (matches the PyInstaller build's default)
            let data_dir = app.path().app_data_dir().ok();

            let cmd = app.shell().sidecar("aec-bim-server");
            let cmd = match cmd {
                Ok(c) => c,
                Err(e) => {
                    // dev / sidecar-less build: keep loading the configured frontend
                    eprintln!("sidecar 'aec-bim-server' unavailable ({e}); loading frontend directly");
                    return Ok(());
                }
            };
            let mut cmd = cmd
                .env("AEC_PORT", PORT.to_string())
                .env("AEC_OPEN_BROWSER", "0");   // the WebView is the UI, not a browser tab
            if let Some(d) = data_dir {
                cmd = cmd.env("AEC_DATA_DIR", d.to_string_lossy().to_string());
            }

            match cmd.spawn() {
                Ok((mut rx, child)) => {
                    // hold the child for the app's lifetime; dropping it (on exit) kills the backend
                    tauri::async_runtime::spawn(async move {
                        let _child = child;
                        while rx.recv().await.is_some() { /* drain stdout/stderr */ }
                    });
                    // when the port is listening, navigate the window to the local server (same-origin)
                    if let Some(win) = app.get_webview_window("main") {
                        std::thread::spawn(move || {
                            for _ in 0..160 {   // ~40s
                                if std::net::TcpStream::connect(("127.0.0.1", PORT)).is_ok() {
                                    if let Ok(url) = format!("http://127.0.0.1:{PORT}/").parse() {
                                        let _ = win.navigate(url);
                                    }
                                    return;
                                }
                                std::thread::sleep(std::time::Duration::from_millis(250));
                            }
                            eprintln!("backend did not start within timeout");
                        });
                    }
                }
                Err(e) => eprintln!("failed to spawn backend sidecar: {e}"),
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running AEC BIM Platform");
}
