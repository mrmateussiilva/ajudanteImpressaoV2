$ErrorActionPreference = "Stop"

Write-Host "Iniciando compilação com Nuitka..." -ForegroundColor Cyan

# Garante que as dependências estão atualizadas
uv sync

# Executa o Nuitka com as flags necessárias para o projeto
python -m nuitka `
    --onefile `
    --plugin-enable=pyside6 `
    --include-package=cv2 `
    --include-package=PIL `
    --include-package=numba `
    --include-package=numpy `
    --include-package=ezdxf `
    --windows-console-mode=disable `
    --output-filename=StudioImpressao.exe `
    main.py

Write-Host "Compilação concluída! O executável StudioImpressao.exe foi gerado na raiz." -ForegroundColor Green
