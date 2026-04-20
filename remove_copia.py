import os
import shutil


path =  "/home/mateus/Documentos/Projetcts/Pessoais/ajudanteImpressaoV2/data"
os.chdir(path)
for file in os.listdir(path):
    if "Cópia" in file:
        os.remove(file)

