# 📡 Spécification du Protocole IoT SmartPower (v2.0)
> **Norme de communication MQTT & LAN pour firmware ESP32 et applications SmartPower**

---

## 1. Vue d'Ensemble des Topics MQTT

Tous les topics respectent la convention de nommage hiérarchique :
```text
sp/v2/{deviceId}/{subtopic}
```

Où `{deviceId}` est l'identifiant matériel unique de 6 à 12 caractères hexadécimaux (ex: `F2ED08`).

| Topic | Sens | Rôle | QOS | Retain |
| :--- | :---: | :--- | :---: | :---: |
| `sp/v2/{id}/status` | ESP32 ➔ Cloud | Disponibilité réseau (`online` ou `offline`) | 1 | **true** (LWT) |
| `sp/v2/{id}/info` | ESP32 ➔ Cloud | Métadonnées matérielles au démarrage | 1 | **true** |
| `sp/v2/{id}/state` | ESP32 ➔ Cloud | État actuel en direct (relais, capteurs) | 1 | **true** |
| `sp/v2/{id}/cmd` | Cloud ➔ ESP32 | Ordres de contrôle envoyés à la carte | 1 | **false** |
| `sp/v2/{id}/energy` | ESP32 ➔ Cloud | Relevés de consommation haute fréquence | 0 | **false** |
| `sp/v2/{id}/ota` | Cloud ➔ ESP32 | Notification de mise à jour firmware | 1 | **false** |

---

## 2. Schémas des Messages JSON

### A. Présence Réseau (`status`)
Défini comme **Last Will and Testament (LWT)** par le broker lors de la connexion MQTT :
```text
"online"   // Publié par l'ESP32 dès que la connexion MQTT réussit
"offline"  // Publié automatiquement par le Broker si la connexion est perdue
```

---

### B. Informations Système (`info`)
Publié une seule fois au boot par l'appareil :
```json
{
  "model": "SP-SW1",
  "firmware": "2.1.0",
  "chip": "ESP32-D0WDQ6",
  "mac": "0c:b8:15:f2:ed:08",
  "ip": "192.168.0.119",
  "rssi": -58,
  "uptime": 1420,
  "freeHeap": 182400
}
```

---

### C. État des Canaux (`state`)
Publié immédiatement lors d'un basculement de relais (via bouton physique ou commande cloud) :

#### Profil Monocanal (Switch 1-CH) :
```json
{
  "switch": "on"
}
```

#### Profil Multicanal (Switch 4-CH) :
```json
{
  "switches": [
    { "switch": "on", "outlet": 0 },
    { "switch": "off", "outlet": 1 },
    { "switch": "on", "outlet": 2 },
    { "switch": "off", "outlet": 3 }
  ]
}
```

---

### D. Ordre de Contrôle (`cmd`)
Envoyé par l'application mobile ou le moteur de scénarios :

```json
{
  "switch": "off"
}
```
Ou pour un canal spécifique sur boîtier multicanal :
```json
{
  "outlet": 2,
  "switch": "toggle"
}
```

---

### E. Télémétrie Énergétique (`energy`)
Émis périodiquement (ex: toutes les 15 secondes si l'appareil est allumé) :

```json
{
  "voltage": 229.4,
  "current": 4.35,
  "power": 998.0,
  "powerFactor": 0.98,
  "energyKwhTotal": 142.85,
  "timestamp": 1792884000
}
```

---

## 3. Protocole d'Appairage & Provisioning

### Phase 1 : Détection & Portail Captif (SoftAP)
- Lorsque la carte n'est pas encore configurée ou si les identifiants Wi-Fi sont perdus, elle crée un réseau ouvert :  
  `ESP32-SmartPower-{ID}`
- L'utilisateur se connecte, une fenêtre s'ouvre automatiquement sur `http://192.168.4.1`.
- L'API REST embarquée suivante est appelée par l'application :

```http
POST /api/provision
Content-Type: application/json

{
  "ssid": "SWEET-HOME",
  "password": "MonMotDePasse",
  "deviceId": "F2ED08",
  "deviceSecret": "sec_7f9b8c2d1e0a",
  "mqttBroker": "mqtt.smartpower.tn",
  "mqttPort": 8883
}
```

---

## 4. API Locale LAN Hors-Ligne (Mode DIY / Zeroconf)

Pour garantir que la maison fonctionne **même si la connexion Internet est coupée**, chaque ESP32 annonce son service localement via mDNS :
```text
_smartpower._tcp.local
Port: 80
TXT: id=F2ED08, model=SP-SW1, type=switch
```

L'application mobile détecte l'ESP32 sur le réseau local et peut commuter le relais directement en HTTP sans passer par le Cloud :
```http
POST http://192.168.0.119/zeroconf/switch
Content-Type: application/json

{
  "switch": "on"
}
```
Réponse :
```json
{
  "error": 0,
  "switch": "on"
}
```
