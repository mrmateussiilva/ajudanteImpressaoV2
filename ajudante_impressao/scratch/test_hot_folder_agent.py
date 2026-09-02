import time
import shutil
from pathlib import Path
from PIL import Image, ImageDraw
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from ajudante_impressao.services.hot_folder_service import HotFolderConfig, HotFolderWorker

def test_hot_folder_simulation():
    scratch_dir = Path(__file__).parent / "test_hotfolder_env"
    if scratch_dir.exists():
        shutil.rmtree(scratch_dir)

    input_dir = scratch_dir / "Entrada_Artes"
    output_dir = scratch_dir / "Rolos_Prontos"
    input_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)

    print(f"Ambiente de teste criado em: {scratch_dir}")

    config = HotFolderConfig(
        input_folder=input_dir,
        output_folder=output_dir,
        largura_cm=120.0,
        margem_cm=0.5,
        espaco_cm=0.3,
        step_px=8,
        allow_rotate=True,
        performance_mode="fast",
        inactivity_seconds=2, # 2 segundos para o teste ser rápido
        settle_seconds=1,     # 1 segundo de estabilização
        group_by_material=False, # Gera 1 rolo com todas
        move_processed=True,
    )

    worker = HotFolderWorker(config)
    def safe_log(msg, lvl):
        clean_msg = msg.encode('ascii', errors='replace').decode('ascii').strip()
        print(f"[{lvl.upper()}] {clean_msg}")

    worker.log.connect(safe_log)
    worker.status.connect(lambda s: print(f"[STATUS] {s}"))

    rolls_generated = []
    worker.roll_completed.connect(lambda res: rolls_generated.append(res))

    print("\n1. Iniciando o Agente Monitorador...")
    worker.start()

    # Simular designer salvando 3 artes na pasta
    print("\n2. Simulando designer salvando 3 artes na pasta Entrada_Artes...")
    for i in range(3):
        img = Image.new("RGBA", (800, 1000), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.polygon([(50, 50), (750, 200), (700, 950), (50, 900)], fill=(50 + i*60, 150, 200, 255))
        file_path = input_dir / f"arte_cliente_{i+1}.png"
        img.save(file_path)
        print(f"   -> Salvo no disco: {file_path.name}")

    # Simular o loop de ticks do agente
    print("\n3. Executando ticks do Agente por 6 segundos...")
    for t in range(7):
        time.sleep(1.0)
        worker._tick()

    worker.stop()

    print("\n4. Verificando resultados do Agente:")
    print(f"   * Rolos gerados: {len(rolls_generated)}")
    assert len(rolls_generated) > 0, "Deveria ter gerado pelo menos 1 rolo!"
    roll = rolls_generated[0]
    print(f"   * Arquivo do rolo: {roll.output_path.name}")
    print(f"   * Arquivo existe no disco: {roll.output_path.exists()}")
    assert roll.output_path.exists(), "O arquivo do rolo gerado deve existir no disco!"

    # Verificar se as artes originais foram movidas para Processados_YYYY-MM-DD
    proc_folders = list(input_dir.glob("Processados_*"))
    print(f"   * Pasta de processados criada: {[p.name for p in proc_folders]}")
    assert len(proc_folders) > 0, "A subpasta Processados_YYYY-MM-DD deveria ter sido criada!"
    moved_files = list(proc_folders[0].glob("*.png"))
    print(f"   * Artes movidas para backup: {[f.name for f in moved_files]}")
    assert len(moved_files) == 3, "As 3 artes deveriam ter sido movidas para a subpasta de processados!"

    print("\n>>> TESTE DO AGENTE MONITORADOR CONCLUIDO COM 100% DE SUCESSO! <<<\n")

if __name__ == "__main__":
    test_hot_folder_simulation()
