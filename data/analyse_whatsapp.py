import re
import pandas as pd
from collections import Counter

# --- 1. Parsing du fichier export WhatsApp ---
# Format des lignes : "DD/MM/YYYY, H:MM après-midi/soir/matin/nuit - Nom: message"
# Les messages sans ce préfixe sont la suite du message précédent (retour à la ligne).

LINE_RE = re.compile(
    r'^(\d{2}/\d{2}/\d{4}), (\d{1,2}:\d{2}) (matin|après-midi|soir|nuit) - ([^:]+): (.*)$'
)

def convert_hour(h_str, period):
    h, m = map(int, h_str.split(':'))
    if period in ('après-midi', 'soir') and h != 12:
        h += 12
    if period == 'nuit' and h == 12:
        h = 0
    return h, m

def parse_whatsapp(path):
    records = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            m = LINE_RE.match(line)
            if m:
                date_str, time_str, period, sender, msg = m.groups()
                h, mnt = convert_hour(time_str, period)
                day, month, year = map(int, date_str.split('/'))
                dt = pd.Timestamp(year=year, month=month, day=day, hour=h, minute=mnt)
                records.append({'datetime': dt, 'sender': sender.strip(), 'message': msg})
            else:
                # ligne de continuation -> on la rattache au dernier message
                if records and line.strip():
                    records[-1]['message'] += '\n' + line

    df = pd.DataFrame(records)
    return df

df = parse_whatsapp('/mnt/user-data/uploads/discussion.txt')

# On enlève la ligne d'info système (chiffrement) et les entrées sans vrai expéditeur
df = df[~df['sender'].str.contains('chiffrés', na=False)]

print(f"Nombre total de messages : {len(df)}")
print(f"Période : du {df['datetime'].min()} au {df['datetime'].max()}")
print()

# --- 2. Répartition par personne ---
print("Messages par personne :")
print(df['sender'].value_counts())
print()

# --- 3. Répartition par jour de la semaine / heure ---
df['jour_semaine'] = df['datetime'].dt.day_name()
df['heure'] = df['datetime'].dt.hour

print("Messages par heure de la journée (top 5) :")
print(df['heure'].value_counts().sort_index().tail(24).sort_values(ascending=False).head(5))
print()

# --- 4. Longueur moyenne des messages par personne ---
df['longueur'] = df['message'].str.len()
print("Longueur moyenne des messages par personne :")
print(df.groupby('sender')['longueur'].mean().round(1))
print()

# --- 5. Médias envoyés (photos/vidéos/fichiers/audios non exportés) ---
df['est_media'] = df['message'].str.contains('Médias omis', na=False)
print("Nombre de médias envoyés par personne :")
print(df[df['est_media']].groupby('sender').size())
print()

# --- 6. Fréquence des mots (hors médias et mots vides basiques) ---
stopwords = set("""le la les un une des de du et est ce que qui je tu il elle on nous vous
ils elles pas ne se sa son ses au aux dans pour avec sur par plus moins mais ou où donc
si oui non c'est j'ai t'as m'a n'ai d'accord ce message a été modifié vous avez supprimé""".split())

def tokenize(texts):
    words = []
    for t in texts:
        words.extend(re.findall(r"[a-zàâçéèêëîïôûùüÿñæœ']+", t.lower()))
    return [w for w in words if w not in stopwords and len(w) > 2]

# on exclut les messages "Médias omis" et les notifs de modif/suppression
df_texte = df[~df['est_media'] & ~df['message'].str.contains('Vous avez supprimé|Ce message a été modifié', na=False)]

for sender, group in df_texte.groupby('sender'):
    words = tokenize(group['message'])
    top = Counter(words).most_common(10)
    print(f"Mots les plus fréquents de {sender} :", top)
print()

# --- 6. Messages par mois (évolution dans le temps) ---
df['mois'] = df['datetime'].dt.to_period('M')
print("Messages par mois :")
print(df.groupby('mois').size())
print()

# --- 7. Temps de réponse moyen entre les 2 personnes ---
df_sorted = df.sort_values('datetime').reset_index(drop=True)
delais = []
for i in range(1, len(df_sorted)):
    if df_sorted.loc[i, 'sender'] != df_sorted.loc[i-1, 'sender']:
        delta = (df_sorted.loc[i, 'datetime'] - df_sorted.loc[i-1, 'datetime']).total_seconds() / 60
        if 0 <= delta < 180:  # on ignore les délais > 3h (probablement une pause, pas une non-réponse)
            delais.append({'sender': df_sorted.loc[i, 'sender'], 'delai_min': delta})

delais_df = pd.DataFrame(delais)
print("Délai de réponse moyen (en minutes, hors pauses > 3h) :")
print(delais_df.groupby('sender')['delai_min'].mean().round(1))

# Export vers un CSV propre pour explorer ailleurs (Excel, etc.)
# encoding='utf-8-sig' -> BOM pour qu'Excel détecte l'UTF-8 correctement
df.to_csv('/mnt/user-data/outputs/discussion_parsee.csv', index=False, encoding='utf-8-sig')
