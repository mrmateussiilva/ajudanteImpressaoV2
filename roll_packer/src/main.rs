mod engine;
mod gui;

use eframe::egui;
use gui::app::RollPackerApp;

fn main() -> eframe::Result<()> {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1024.0, 768.0])
            .with_title("Roll Packer"),
        ..Default::default()
    };
    eframe::run_native(
        "Roll Packer",
        options,
        Box::new(|_cc| Ok(Box::new(RollPackerApp::default()))),
    )
}
