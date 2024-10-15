import requests
import os
from django.conf import settings
import re
import logging
from pathlib import Path
from django.shortcuts import render
from django.http import JsonResponse
import whisper
from openai import OpenAI

# Inicializando o cliente OpenAI
client = OpenAI(api_key='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')  # Insira sua chave da API aqui
logger = logging.getLogger(__name__)

# Inicializa uma lista para armazenar o histórico de mensagens
chat_history = []



def sanitize_filename(text):
    return re.sub(r'\W+', '_', text.strip())

# Função para conversão de áudio para texto
def audio_to_text(file_path):
    with open(file_path, "rb") as audio_file:
        try:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            )

            # Verifica se a transcrição é uma string
            if isinstance(transcription, str):
                return transcription  # Retorna a transcrição diretamente

            logger.error(f"Resposta inesperada da API: {transcription}")
            return "Erro ao transcrever o áudio."

        except Exception as e:
            logger.error(f"Erro ao transcrever o áudio: {e}")
            return "Erro ao transcrever o áudio."

def generate_code_response(prompt):
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "Você é um assistente que ajuda a gerar código fonte."},
            {"role": "user", "content": prompt}
        ]
    )
    
    # Adiciona as marcações de código
    code = response.choices[0].message.content.strip()
    return f"```\n{code}\n```"  # Retorna o código gerado com formatação

# Função para conversão de texto para áudio
import os
from pathlib import Path
import logging

# Configura o logger
logger = logging.getLogger(__name__)

def text_to_audio(text, output_filename="speech.mp3"):
    # Converte o nome do arquivo para um objeto Path
    output_filename = Path(output_filename)

    # Define o diretório de saída como a raiz do projeto
    output_dir = Path(__file__).resolve().parent.parent / "static" / "audio"
    os.makedirs(output_dir, exist_ok=True)  # Cria o diretório se não existir

    # Gera um nome de arquivo auto-incremental
    base_filename = output_filename.stem  # Nome sem extensão
    extension = output_filename.suffix  # Extensão do arquivo
    speech_file_path = output_dir / output_filename  # Caminho inicial

    # Incrementa o número no nome do arquivo se já existir
    counter = 1
    while speech_file_path.exists():
        speech_file_path = output_dir / f"{base_filename}_{counter}{extension}"
        counter += 1

    print(f'Salvando áudio em: {speech_file_path}')  # Mostra o caminho onde o áudio será salvo

    try:
        # Usando a nova API da OpenAI para gerar áudio
        response = client.audio.speech.create(
            model="tts-1",
            voice="nova",  # Especifique a voz desejada
            input=text
        )

        # Salva o áudio retornado em um arquivo
        with open(speech_file_path, "wb") as audio_file:
            audio_file.write(response.content)  # Acessa o conteúdo diretamente
        print(f'Áudio salvo com sucesso em: {speech_file_path}')

    except Exception as e:
        logger.error(f'Erro ao gerar áudio: {e}')
        return None  # Lide com o erro de forma apropriada

    return speech_file_path


# Função para gerar imagem a partir do texto (Usando DALL-E)
def generate_image(prompt):
    response = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024",  # Tamanho ajustado para um suportado
        quality="standard",
        n=1,
    )

    # Acesso correto ao conteúdo da resposta
    image_url = response.data[0].url

    # Fazendo o download da imagem
    image_response = requests.get(image_url)
    if image_response.status_code == 200:
        # Cria o diretório se não existir
        img_directory = os.path.join(settings.BASE_DIR, 'static', 'img')
        os.makedirs(img_directory, exist_ok=True)

        # Nome do arquivo da imagem
        image_name = f"{prompt.replace(' ', '_')}.png"  # ou outra extensão se necessário
        image_path = os.path.join(img_directory, image_name)

        # Salva a imagem no diretório especificado
        with open(image_path, 'wb') as img_file:
            img_file.write(image_response.content)

        return f'/static/img/{image_name}'  # Retorna o caminho da imagem salva
    else:
        raise Exception("Falha ao baixar a imagem.")

# Função para gerar resposta de texto (Usando ChatGPT)
def generate_text_response(prompt):
    # Adiciona a mensagem do usuário ao histórico
    chat_history.append({"role": "user", "content": prompt})
    
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=chat_history  # Passa o histórico de mensagens
    )
    
    # Acesso correto ao conteúdo da mensagem
    bot_response = response.choices[0].message.content.strip()
    
    # Adiciona a resposta do bot ao histórico
    chat_history.append({"role": "assistant", "content": bot_response})
    
    return bot_response  # Retorna a resposta do bot

# View do Chatbot
def chat_view(request):
    if request.method == 'GET':
        return render(request, 'chat.html')

    elif request.method == 'POST':
        user_message = request.POST.get('message')
        mode = request.POST.get('mode')
        logger.debug(f'Mensagem do usuário: {user_message}')

        # Se o modo for 'audio_to_text', verifica se o arquivo de áudio foi fornecido
        if mode == 'audio_to_text':
            audio_file = request.FILES.get('audio_file')
            if not audio_file:
                logger.error("Arquivo de áudio não fornecido.")
                return JsonResponse({"error": "No audio file provided"}, status=400)

        # Verifica se a mensagem do usuário foi fornecida, caso o modo não seja 'audio_to_text'
        if not user_message and mode != 'audio_to_text':
            return JsonResponse({"error": "No message provided"}, status=400)

        bot_response = None
        image_url = None
        audio_url = None

        try:
            if mode == 'text':
                bot_response = generate_text_response(user_message)

            elif mode == 'generate_image':
                image_url = generate_image(user_message)

            elif mode == 'text_to_audio':
                output_path = text_to_audio(user_message)
                if output_path is None:
                    return JsonResponse({"error": "Failed to generate audio"}, status=500)
                audio_url = f"/static/audio/{os.path.basename(output_path)}"

            elif mode == 'audio_to_text':
                file_path = os.path.join('media', audio_file.name)
                os.makedirs('media', exist_ok=True)
                with open(file_path, 'wb+') as destination:
                    for chunk in audio_file.chunks():
                        destination.write(chunk)
                bot_response = audio_to_text(file_path)

            elif mode == 'generate_code':
                bot_response = generate_code_response(user_message)

            logger.debug(f'Resposta do bot: {bot_response}, Imagem: {image_url}, Áudio: {audio_url}')
        except Exception as e:
            logger.error(f'Erro ao gerar resposta: {e}')
            return JsonResponse({"error": str(e)}, status=500)

        response_data = {
            'response': bot_response,
            'image_url': image_url,
            'audio_url': audio_url,
        }

        return JsonResponse(response_data)

    return JsonResponse({'error': 'Invalid HTTP method'}, status=405)

