import os
import requests
import re
import logging
import PyPDF2
from django.contrib.sessions.models import Session
from pathlib import Path
from django.shortcuts import render
from django.http import JsonResponse
from django.conf import settings
from openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser



# Inicializando o cliente OpenAI
api_key = ''
os.environ['OPENAI_API_KEY'] = api_key  # Define a variável de ambiente
client = OpenAI(api_key=api_key)  # Insira sua chave da API aqui
if not api_key:
    raise ValueError("Chave da API não configurada. Defina a variável de ambiente OPENAI_API_KEY.")
logger = logging.getLogger(__name__)

# Verificando se a chave da API está definida corretamente


model = ChatOpenAI(model='gpt-3.5-turbo')
# Inicializa uma lista para armazenar o histórico de mensagens
chat_history = []


def file_upload(file_path):
    try:
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text
                else:
                    logger.warning("Nenhum texto extraído da página.")
            return text if text else "Nenhum texto extraído."
    except Exception as e:
        logger.error(f'Erro ao processar o PDF: {e}')
        return "Erro ao processar o arquivo PDF."


# Função para gerar respostas com base no conhecimento do arquivo
def generate_response_with_document(contexto, pergunta):
    prompt_base_conhecimento = PromptTemplate(
        input_variables=['contexto', 'pergunta'],
        template='''Use o seguinte contexto para responder à pergunta.
                    Responda apenas com base nas informações fornecidas caso o usuário queria saber do arquivo.
                    Não utilize informações externas ao contexto:
                    Contexto: {contexto}
                    Pergunta: {pergunta}'''
    )
    chain = prompt_base_conhecimento | model | StrOutputParser()
    response = chain.invoke({'contexto': contexto, 'pergunta': pergunta})
    return response

# View para upload de arquivos e resposta baseada no arquivo
def upload_and_ask_view(request):
    if request.method == 'POST':
        uploaded_file = request.FILES.get('file')
        pergunta = request.POST.get('pergunta')

        if not uploaded_file or not pergunta:
            return JsonResponse({"error": "Documento ou pergunta não fornecidos."}, status=400)

        try:
            # Salvar o arquivo enviado
            file_path = os.path.join('media', sanitize_filename(uploaded_file.name))
            with open(file_path, 'wb+') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)

            # Carregar e processar o arquivo
            contexto = file_upload(file_path)
            bot_response = generate_response_with_document(contexto, pergunta)

            return JsonResponse({'response': bot_response})
        
        except Exception as e:
            logger.error(f"Erro ao processar o arquivo: {e}")
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({'error': 'Invalid HTTP method'}, status=405)

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

chat_history = [
    {
        "role": "system",
        "content": (
            "Você é um assistente virtual que se chama Nymira. "
            "Seja educado, amigável e ajude o Usuário com o que ela precisar."
        )
    }
]
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
        logger.debug(f'Mensagem do usuário: {user_message}, Modo: {mode}')

        bot_response = None
        image_url = None
        audio_url = None

        # Se o modo for 'audio_to_text', verifica se o arquivo de áudio foi fornecido
        if mode == 'audio_to_text':
            audio_file = request.FILES.get('audio_file')
            if not audio_file:
                logger.error("Arquivo de áudio não fornecido.")
                return JsonResponse({"error": "No audio file provided"}, status=400)

        # Verifica se a mensagem do usuário foi fornecida, caso o modo não seja 'audio_to_text'
        if not user_message and mode != 'audio_to_text' and mode != 'file_upload':
            logger.error("Mensagem do usuário não fornecida.")
            return JsonResponse({"error": "No message provided"}, status=400)

        try:
            if mode == 'text':
                contexto = request.session.get('contexto')
                
                # Verifica se a pergunta é sobre o documento
                if "documento" in user_message.lower() and contexto:
                    bot_response = generate_response_with_document(contexto, user_message)
                else:
                    # Gera uma resposta geral se não for sobre o documento
                    bot_response = generate_text_response(user_message)

            elif mode == 'file_upload':
                uploaded_file = request.FILES.get('file')
                if not uploaded_file:
                    logger.error("Documento não fornecido.")
                    return JsonResponse({"error": "No file provided"}, status=400)

                # Salvar o arquivo
                file_path = os.path.join('media', sanitize_filename(uploaded_file.name))
                os.makedirs('media', exist_ok=True)
                with open(file_path, 'wb+') as destination:
                    for chunk in uploaded_file.chunks():
                        destination.write(chunk)

                # Carregar e processar o arquivo
                contexto = file_upload(file_path)  # Extrair texto do PDF
                logger.debug(f'Contexto extraído: {contexto}')
                
                # Armazenar contexto na sessão
                request.session['contexto'] = contexto

                bot_response = "Documento carregado com sucesso! Agora você pode fazer perguntas sobre o conteúdo."

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



