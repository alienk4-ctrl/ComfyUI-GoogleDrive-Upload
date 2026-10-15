
# ComfyUI Google Drive Upload — Kaggle

Nó personalizado para enviar imagens diretamente do ComfyUI
ao Google Drive, sem salvar as imagens em arquivos locais.

## Requisitos

- ComfyUI instalado.
- Google Drive API habilitada no Google Cloud.
- Secret `GDRIVE_TOKEN_JSON` configurado no Kaggle.
- A credencial deve ter acesso à pasta de destino.

## Instalação

Dentro de `ComfyUI/custom_nodes`:

```bash
git clone https://github.com/theclueless-ai/comfyui-google-drive-upload.git \
  ComfyUI-GoogleDrive-Upload

cd ComfyUI-GoogleDrive-Upload
pip install -r requirements.txt
```

Substitua os arquivos do repositório pelos arquivos desta versão
adaptada para Kaggle e reinicie o ComfyUI.

## Configuração do secret

No Kaggle, abra Add-ons > Secrets e crie:

- Nome: `GDRIVE_TOKEN_JSON`
- Valor: JSON válido da credencial Google.

Ative o acesso do notebook ao secret.

O nó lê o secret durante a execução e não o grava em arquivo.

## Workflow

Conecte:

`Gerador de imagem → Upload to Google Drive (Kaggle)`

Configure:

- `folder_id`: ID ou URL da pasta do Drive.
- `filename_prefix`: prefixo do nome do arquivo.
- `image_format`: PNG, JPEG ou WEBP.
- `jpeg_quality`: qualidade de JPEG/WEBP.
- `add_timestamp`: acrescenta data e hora ao nome.

## Memória e armazenamento

As imagens são convertidas em buffers `io.BytesIO` e enviadas
pela API do Google Drive. Nenhum arquivo PNG, JPEG ou WEBP
intermediário é criado pelo nó.

O ComfyUI e outros nós do workflow ainda podem usar disco
para checkpoints, caches, pré-visualizações ou outros outputs.

## Permissões

Para uma Service Account, compartilhe a pasta de destino
com o e-mail `client_email` da credencial.

Para OAuth, use uma credencial de usuário válida com acesso
à pasta de destino.

## Licença

Consulte a licença do repositório original.
