import subprocess
import sys
from pathlib import Path

def main():
    print("Iniciando compilação com Nuitka...")

    # Garante que as dependências estão instaladas usando uv
    try:
        subprocess.run(["uv", "sync"], check=True)
    except subprocess.CalledProcessError:
        print("Erro ao executar 'uv sync'. Certifique-se de que o uv está instalado e configurado.")
        sys.exit(1)

    # Executa o Nuitka com as flags formatadas como uma lista
    command = [
        sys.executable, "-m", "nuitka",
        "--onefile",
        "--plugin-enable=pyside6",
        "--include-package=cv2",
        "--include-package=PIL",
        "--include-package=numba",
        "--include-package=numpy",
        "--include-package=ezdxf",
        "--windows-console-mode=disable",
        "--output-filename=StudioImpressao.exe",
        "main.py"
    ]

    print("Executando: " + " ".join(command))
    
    try:
        # Chama o processo e envia a saída direto pro terminal
        result = subprocess.run(command)
        if result.returncode == 0:
            print("\n✅ Compilação concluída! O executável StudioImpressao.exe foi gerado na raiz.")
        else:
            print(f"\n❌ O Nuitka falhou com o código de saída {result.returncode}.")
            sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\n⚠ Compilação cancelada pelo usuário.")
        sys.exit(1)

if __name__ == "__main__":
    main()
