# Monitor de figure no Mercari Japão (jp.mercari.com)

Script que busca uma figure pelo nome/descrição no Mercari JP e te avisa no
Telegram quando encontrar um anúncio dentro do preço que você definir.

Usa a biblioteca [`mercapi`](https://github.com/take-kun/mercapi), que fala
com a API interna do Mercari (a mesma que o site usa), então não depende de
"ler" o HTML da página — é mais estável que scraping tradicional.

> ⚠️ Isso não é uma API oficial do Mercari. Use para uso pessoal, sem exagerar
> na frequência de checagens (6x/dia é tranquilo) para não correr risco de
> bloqueio.

## 1. Criar o bot no Telegram

1. No Telegram, procure o bot **@BotFather** e envie `/newbot`.
2. Siga as instruções e guarde o **token** que ele te der (algo como
   `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`).
3. Envie qualquer mensagem para o bot que você criou (procure ele pelo
   username escolhido e clique em "Iniciar").
4. Abra no navegador, trocando `<TOKEN>` pelo token do passo 2:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
5. Procure o campo `"chat":{"id":123456789...` — esse número é o seu
   `telegram_chat_id`.

## 2. Instalar as dependências

```bash
pip install -r requirements.txt
```

(Se dependendo do seu sistema for necessário, use `pip install -r requirements.txt --break-system-packages`.)

## 3. Configurar

Copie o arquivo de exemplo:

```bash
cp config.example.json config.json
```

Edite `config.json`:

- `search_query`: termo de busca (ex: `"figure Nendoroid Miku"`)
- `must_include_words`: palavras que **precisam** aparecer no título do
  anúncio para ele contar como um resultado válido (ajuda a filtrar
  produtos parecidos que não são a figure certa)
- `must_exclude_words`: palavras que, se aparecerem no título, descartam o
  anúncio (ex: "quebrada", "sem caixa", "réplica")
- `price_max`: preço máximo em **ienes (¥)** — o Mercari Japão trabalha em ienes
- `telegram_bot_token` e `telegram_chat_id`: dados do passo 1

## 4. Rodar manualmente (teste)

```bash
python monitor_mercari.py
```

Se tudo estiver certo, você verá logs no terminal e (se achar algo dentro do
preço) receberá uma mensagem no Telegram. Um arquivo `state.json` é criado
automaticamente para lembrar quais anúncios já foram notificados, evitando
que você receba o mesmo alerta repetido toda vez que o script rodar — só
avisa de novo se o preço cair ainda mais.

## 5. Agendar para rodar 6x por dia

Você disse que ainda não sabe onde vai rodar — aqui vão as 3 opções mais
comuns:

### Opção A — Seu computador ligado (Linux/Mac) via cron

```bash
crontab -e
```

Adicione (roda às 6h, 10h, 14h, 18h, 22h e 2h):

```
0 6,10,14,18,22,2 * * * cd /caminho/para/mercari_monitor && /usr/bin/python3 monitor_mercari.py >> log.txt 2>&1
```

### Opção B — Windows (Task Scheduler / Agendador de Tarefas)

1. Abra o "Agendador de Tarefas" → "Criar Tarefa Básica".
2. Defina o gatilho como "Diariamente" e configure para repetir a cada 4
   horas (na aba de configurações avançadas do gatilho).
3. Ação: "Iniciar um programa" → aponte para `python.exe`, com argumento
   `monitor_mercari.py` e "Iniciar em" apontando para a pasta do script.

### Opção C — GitHub Actions (grátis, roda sozinho na nuvem) ✅ já configurado

O workflow `.github/workflows/monitor.yml` já vem pronto no projeto e roda o
script automaticamente 6x por dia (a cada 4h), sem precisar deixar seu
computador ligado. Veja a seção **"Rodando no GitHub Actions"** abaixo.

## Rodando no GitHub Actions

Assim o script roda sozinho na nuvem, de graça, sem depender do seu PC ligado.

### 1. Criar o repositório

1. Crie um repositório novo no GitHub (pode ser **privado** — recomendado,
   já que ele guarda seus critérios de busca).
2. Suba todos os arquivos desta pasta para o repositório, **exceto**
   `config.json` com token preenchido (não existe nesse caso — veja abaixo)
   e a pasta local `state.json` se já tiver rodado antes (pode subir vazio).

### 2. Configurar o `config.json` do repositório

No GitHub Actions, o token e o chat ID do Telegram **não** ficam no
`config.json` — ficam em *Secrets* (passo 4). Então o `config.json` que vai
para o repositório deve ter os campos de Telegram vazios:

```json
{
  "search_query": "figure Nendoroid Miku",
  "must_include_words": ["Miku", "figure"],
  "must_exclude_words": ["quebrada", "réplica"],
  "price_max": 8000,
  "telegram_bot_token": "",
  "telegram_chat_id": ""
}
```

Renomeie `config.example.json` para `config.json`, edite os critérios de
busca e faça commit dele normalmente (sem token, não tem problema ficar
público).

### 3. Criar um `state.json` vazio

Crie um arquivo `state.json` com `{}` dentro e suba pro repositório — assim
o workflow tem o que atualizar a cada execução.

### 4. Adicionar os Secrets

No repositório: **Settings → Secrets and variables → Actions → New
repository secret**. Crie dois secrets:

- `TELEGRAM_BOT_TOKEN` → o token do seu bot
- `TELEGRAM_CHAT_ID` → o seu chat ID

### 5. Permitir que o workflow faça commit

O workflow precisa salvar o `state.json` atualizado a cada execução (pra não
repetir alertas). Isso já está configurado no `monitor.yml`
(`permissions: contents: write`), mas em alguns repositórios você também
precisa habilitar manualmente em: **Settings → Actions → General → Workflow
permissions → marcar "Read and write permissions"** → Salvar.

### 6. Testar

Vá na aba **Actions** do repositório → selecione o workflow "Monitor
Mercari" → **Run workflow** (botão à direita) para testar manualmente antes
de esperar o agendamento automático.

### Sobre o agendamento

O cron do workflow (`0 0,4,8,12,16,20 * * *`) roda a cada 4 horas em UTC —
ajuste os horários no arquivo `.github/workflows/monitor.yml` se quiser
horários diferentes. Vale saber que o GitHub Actions:
- Pode atrasar alguns minutos a execução agendada (não é 100% pontual).
- **Desativa workflows agendados automaticamente após 60 dias sem nenhuma
  atividade no repositório** — se isso acontecer, basta reativar manualmente
  na aba Actions.

## Observações

- O Mercari pode mudar o site/API e quebrar o script eventualmente — é
  normal precisar de manutenção de vez em quando.
- `price_max` é em ienes; se quiser converter para reais só para
  conferência, pode usar qualquer conversor online.
- Rodar 6x/dia (a cada ~4h) é um intervalo seguro; evite deixar rodando a
  cada poucos minutos.
