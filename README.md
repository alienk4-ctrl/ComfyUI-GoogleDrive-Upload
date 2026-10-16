
# ComfyUI Google Drive Upload — Kaggle

Custom nodes para enviar imagens e vídeos do ComfyUI ao Google Drive.

- Upload de imagens em memória, sem criar arquivos intermediários.
- Upload de vídeos existentes em blocos, sem criar uma segunda cópia.
- Autenticação OAuth ou Google Service Account.
- Suporte a pastas do Google Drive por ID ou URL.

## Requisitos

- ComfyUI instalado.
- Google Drive API habilitada no Google Cloud.
- Secret `GDRIVE_TOKEN_JSON` configurado no Kaggle, quando executado nesse ambiente.
- Credenciais com acesso à pasta de destino.

## Instalação

Dentro de `ComfyUI/custom_nodes`:

```bash
git clone https://github.com/theclueless-ai/comfyui-google-drive-upload.git ComfyUI-GoogleDrive-Upload

cd ComfyUI-GoogleDrive-Upload

pip install -r requirements.txt
```

Reinicie o ComfyUI após a instalação.

## Configuração do secret

No Kaggle, abra Add-ons > Secrets e crie:

- Nome: `GDRIVE_TOKEN_JSON`
- Valor: JSON válido da credencial Google.

Ative o acesso do notebook ao secret.

O código consulta o secret durante a execução e não o grava em arquivo.

Nunca publique tokens, chaves privadas ou credenciais no GitHub.

## Nó de upload de imagens

Nó: `Upload Image to Google Drive`

Entradas:

- `image`: imagem do ComfyUI.
- `folder_id`: ID ou URL da pasta do Drive.
- `filename_prefix`: prefixo do nome do arquivo.
- `image_format`: PNG, JPEG ou WEBP.
- `jpeg_quality`: qualidade de JPEG ou WEBP.
- `add_timestamp`: acrescenta data e hora ao nome.

Saídas:

- `status`: resultado do upload.
- `file_url`: link para o arquivo no Drive.

Workflow:

`Gerador de imagem → Upload Image to Google Drive`

As imagens são convertidas em buffers de memória antes do upload.

## Nó de upload de vídeos

Nó: `Upload Video to Google Drive`

Entradas:

- `video_path`: caminho do arquivo de vídeo gerado pelo ComfyUI.
- `folder_id`: ID ou URL da pasta do Drive.
- `filename_prefix`: prefixo do nome do arquivo.
- `add_timestamp`: acrescenta data e hora ao nome.
- `chunk_size_mb`: tamanho dos blocos do upload.

Saídas:

- `status`: resultado do upload.
- `file_url`: link para o vídeo no Drive.

Workflow:

1. Gere o vídeo com o VideoHelperSuite (VHS).
2. Informe o caminho completo do arquivo gerado em `video_path`.
3. Configure a pasta de destino.
4. Execute o nó e consulte `status` e `file_url`.

O upload é feito em blocos a partir do arquivo existente. O nó não cria uma segunda cópia do vídeo, mas o arquivo original precisa existir no disco.

## Armazenamento

O nó de imagens não cria arquivos intermediários de imagem.

O nó de vídeos lê o arquivo existente e transmite os dados em blocos.

O ComfyUI e outros nós ainda podem usar disco para outputs,
checkpoints, caches e pré-visualizações.

## Permissões

Para uma Service Account, compartilhe a pasta de destino com o endereço `client_email` da credencial.

Para OAuth, utilize uma credencial válida com acesso à pasta.

## Dependências

As dependências estão declaradas em `requirements.txt`.

Instale-as com:

```bash
pip install -r requirements.txt
```

## Licença

Consulte a licença do repositório original antes de redistribuir
ou publicar versões modificadas.
