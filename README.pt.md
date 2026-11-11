# Yeelight Color (yeelink.light.color2) no Home Assistant — sem app e sem cloud

[English](README.md) | **Português**

Este guia configura uma lâmpada Yeelight Color só com a linha de comandos no Windows. Obtém-se o token, ativa-se o controlo LAN e liga-se a lâmpada ao Wi‑Fi **sem a app Yeelight ou Mi Home e sem conta Xiaomi**. No fim, a lâmpada é adicionada ao Home Assistant pela integração oficial **Yeelight**.

## Configuração rápida (recomendada)

A ferramenta `yeelight-setup` faz por si os passos 3 a 6 do guia manual. Só tem de introduzir o nome e a palavra-passe do Wi‑Fi. Existe em duas versões; escolha uma:

### Opção A — Executável para Windows (sem instalar nada)

1. Descarregue o `yeelight-setup.exe` da página [Releases](../../releases).
2. Reponha as definições de fábrica da lâmpada (passo 1) e ligue o PC à rede dela (passo 2).
3. Faça duplo clique no `yeelight-setup.exe` e siga as instruções.

O Windows SmartScreen pode avisar que a aplicação não é reconhecida, porque não está assinada. Clique em **Mais informações → Executar mesmo assim**. Cada versão inclui também um ficheiro `.sha256`, para confirmar que o ficheiro descarregado é o mesmo que o GitHub Actions compilou a partir do código deste repositório:

```
powershell (Get-FileHash yeelight-setup.exe -Algorithm SHA256).Hash
```

### Opção B — Script Python

Requer Python 3.9 ou mais recente.

```
pip install -r requirements.txt
python yeelight_setup.py
```

### O que a ferramenta faz

1. Encontra a lâmpada na rede de configuração e lê o token, que guarda em `yeelight_token_<id>.txt` na pasta atual.
2. Ativa o controlo LAN.
3. Pede o nome e a palavra-passe do Wi‑Fi (a palavra-passe não aparece no ecrã) e envia-os para a lâmpada. Sabe que é normal a lâmpada desligar a sua rede antes de responder.
4. Pede-lhe para voltar à sua rede habitual, encontra a lâmpada e testa a porta TCP 55443.

A ferramenta fala inglês ou português, conforme a língua do Windows. Pode escolher com `--lang pt` ou `--lang en`. Para ver todas as opções, execute `yeelight_setup.py --help`.

A ferramenta não mexe no router nem na firewall: as regras do passo 7 têm de ser criadas manualmente.

> A ferramenta comunica diretamente com a lâmpada na rede local, pelo protocolo miIO (UDP 54321) e pelo protocolo LAN da Yeelight (TCP 55443). Nada é enviado para a Internet. A única dependência é o `cryptography`.

## Testado com

| Campo | Valor |
|---|---|
| Modelo | `yeelink.light.color2` |
| Firmware | `2.0.6_0065` |
| Hardware | `mw302` |
| Sistema | Windows (cmd / PowerShell) |

Outros modelos `yeelink.light.*` antigos devem funcionar da mesma forma, mas não foram testados.

## Configuração manual — requisitos

- [Node.js](https://nodejs.org/) e a CLI `miio`:
  ```
  npm install -g miio
  ```
- Python 3 e a biblioteca [python-miio](https://github.com/rytilahti/python-miio):
  ```
  pip install python-miio
  ```
- Uma rede Wi‑Fi de **2,4 GHz** com **WPA2**. Evite WPA3 e SSIDs com caracteres especiais.

## Configuração manual — passos

### 1. Repor as definições de fábrica da lâmpada

Ligue e desligue a lâmpada 5 vezes seguidas. A lâmpada pisca e reinicia em modo de configuração, criando uma rede Wi‑Fi própria com um nome como `yeelink-light-color2_miapXXXX`.

### 2. Ligar o PC à rede da lâmpada

No Windows, ligue-se à rede `yeelink-light-color2_miapXXXX`. A lâmpada fica no endereço do gateway dessa rede. Para o ver, execute `ipconfig` e procure *Default Gateway*. Neste guia, esse endereço aparece como `<IP_AP>`.

### 3. Obter o token

```
miio inspect <IP_AP>
```

Exemplo de resposta:

```
Device ID: <DEVICE_ID>
Model info: yeelink.light.color2
Address: <IP_AP>
Token: <TOKEN> via auto-token
Support: At least generic

Firmware version: 2.0.6_0065
Hardware version: mw302

WiFi: Not Connected
```

O token só é revelado automaticamente (`auto-token`) enquanto a lâmpada ainda não está configurada. Guarde-o: vai precisar dele no passo seguinte.

> ⚠️ O token dá controlo total sobre a lâmpada. Nunca o publique.

### 4. Ativar o controlo LAN (modo de programador)

Faça este passo **antes** de ligar a lâmpada ao Wi‑Fi:

```
python -c "from miio import Device; d=Device('<IP_AP>','<TOKEN>'); print(d.send('set_ps',['cfg_lan_ctrl','1']))"
```

Resposta esperada:

```
['ok']
```

Alternativa com a CLI do python-miio:

```
miiocli yeelight --ip <IP_AP> --token <TOKEN> set_developer_mode 1
```

### 5. Ligar a lâmpada ao Wi‑Fi

```
miio configure <IP_AP> --ssid "<SSID>" --passwd "<PALAVRA_PASSE>"
```

**Nota:** este comando pode responder com

```
ERROR  Encountered an error while updating wireless
Failed updating wireless
```

e, mesmo assim, a configuração ter funcionado. A lâmpada desliga a sua rede assim que aceita as credenciais e a CLI perde a ligação antes de receber a confirmação. Volte a ligar o PC à sua rede habitual e procure a lâmpada na lista de clientes DHCP do router.

### 6. Confirmar que o controlo LAN está ativo

Com o PC de novo na sua rede habitual, use o IP que o router atribuiu à lâmpada (`<IP_LAMPADA>`):

```
powershell Test-NetConnection <IP_LAMPADA> -Port 55443
```

Resultado esperado:

```
RemoteAddress    : <IP_LAMPADA>
RemotePort       : 55443
TcpTestSucceeded : True
```

A porta `55443` é a do protocolo LAN da Yeelight. Se a ligação for aceite, o modo de programador está ativo.

> Faça este teste a partir de um PC na **mesma VLAN da lâmpada**. Se a firewall bloquear o tráfego entre VLANs, um teste feito noutra VLAN dá `TcpTestSucceeded : False`, mesmo com o controlo LAN ativo.

### 7. Regras da firewall (Home Assistant e lâmpada em VLANs diferentes)

Exemplo com UniFi, em que a lâmpada está numa VLAN de IoT e o Home Assistant noutra VLAN:

| Regra | Origem | Destino | Porta | Ação |
|---|---|---|---|---|
| HA → Yeelight | IP do Home Assistant | `<IP_LAMPADA>` (ou um grupo com as lâmpadas Yeelight) | TCP `55443` | Permitir |
| Yeelight → Internet | `<IP_LAMPADA>` (ou o grupo) | Internet / External | Todas | Bloquear |

- A primeira regra deixa o Home Assistant controlar a lâmpada. O tráfego de resposta é permitido se a firewall for *stateful* (a da UniFi é).
- A segunda regra é opcional, mas recomendada: a lâmpada continua a funcionar localmente e deixa de receber atualizações automáticas da cloud.
- Para não depender do IP, crie uma **reserva DHCP** para cada lâmpada.

### 8. Adicionar ao Home Assistant

No Home Assistant, vá a **Definições → Dispositivos e serviços**.

- **Mesma VLAN:** a lâmpada é normalmente descoberta automaticamente.
- **VLAN diferente:** a descoberta automática usa multicast e não passa entre VLANs. Use **Adicionar integração → Yeelight** e indique `<IP_LAMPADA>`.

## Resolução de problemas

| Sintoma | Causa provável / solução |
|---|---|
| `miio inspect` não mostra o token | A lâmpada já foi configurada. Reponha as definições de fábrica (passo 1). |
| `Failed updating wireless` | Pode ser um falso erro (ver passo 5). Confirme no router antes de repetir. |
| A lâmpada não aparece no router | Rede de 5 GHz ou WPA3, SSID com caracteres especiais ou palavra-passe errada. Reponha as definições de fábrica da lâmpada e repita a partir do passo 1. |
| `TcpTestSucceeded : False` | Se o teste foi feito noutra VLAN, a firewall está a bloquear o tráfego: repita-o na VLAN da lâmpada. Se falhar na mesma VLAN, o controlo LAN não ficou ativo: repita o passo 4 contra `<IP_LAMPADA>`. |
| O Home Assistant não descobre a lâmpada | A descoberta usa multicast e não passa entre VLANs ou sub-redes. Adicione a lâmpada manualmente pelo IP (passo 8). |
| O Home Assistant não controla a lâmpada | Falta a regra da firewall que permite tráfego do HA para a lâmpada na porta TCP 55443 (passo 7). |

## Segurança

- O controlo LAN da Yeelight **não tem autenticação**: qualquer dispositivo na mesma rede pode controlar a lâmpada. Ponha-a numa VLAN própria para IoT e permita só o tráfego do Home Assistant (passo 7).
- Bloqueie o acesso da lâmpada à Internet (passo 7). Assim evita atualizações de firmware automáticas, que já removeram o controlo LAN em alguns modelos.
- Antes de publicar logs, substitua o token, o Device ID, os IPs, o SSID e a palavra-passe por marcadores.
- Durante a configuração, a rede Wi‑Fi da própria lâmpada é **aberta** e o token passa nela sem cifra, tal como acontece com as apps oficiais. Alguém ao alcance do Wi‑Fi durante esses minutos poderia ler o token e decifrar a palavra-passe do Wi‑Fi enviada para a lâmpada. Faça a configuração em casa e termine-a rapidamente.
- Se responder mais de um dispositivo em modo de configuração, a ferramenta pergunta qual usar. Antes de enviar a palavra-passe do Wi‑Fi, mostra sempre o modelo e o IP e pede confirmação.
- Os ficheiros `yeelight_token_*.txt` criados pela ferramenta estão no `.gitignore`, para não irem parar ao repositório por engano.

## Referências

- [python-miio](https://github.com/rytilahti/python-miio)
- [miio (CLI Node.js) — gestão de dispositivos](https://github.com/aholstenson/miio/blob/master/docs/management.md)
- [Integração Yeelight do Home Assistant](https://www.home-assistant.io/integrations/yeelight/)
