"""Multilingual concept lexicon (~30 European languages + a few more) for the zero-cost rule router.
Each concept maps to word stems; `has(concept, text)` matches on lowercased text with word-start boundaries.
Stems are deliberately short so inflected forms match (e.g. Finnish 'ikkun' -> ikkuna, ikkunaa, ikkunoita)."""
import re, functools, unicodedata

LEX = {
    'door': ['door', 'tür', 'tuer', 'porte', 'porta', 'porte', 'puerta', 'portas', 'deur', 'dörr', 'dør', 'dor ', 'ovi', 'ove', 'ovea', 'ovia', 'ovet',
             'uks', 'ust', 'uste', 'durvis', 'durvju', 'durys', 'durų', 'drzwi', 'dveř', 'dveri', 'dvere', 'dvér', 'vrat', 'ajtó', 'ajtaj', 'uș', 'uş', 'врат', 'двер',
             'πόρτ', 'θύρ', 'kapı', 'kapi', 'porta', 'hurð', 'dora', 'doirse', 'bieb', 'durų'],
    'window': ['window', 'fenster', 'fenêtre', 'fenetre', 'finestr', 'ventana', 'janela', 'raam', 'ramen', 'fönst', 'vindu', 'vindue', 'ikkun', 'aken', 'akna', 'akend',
               'logs', 'logu', 'lang', 'okn', 'okien', 'okno', 'ablak', 'fereastr', 'prozor', 'прозор', 'прозорец', 'окн', 'окон', 'παράθυρ', 'pencere', 'gluggi', 'fuinneog', 'tieqa'],
    'toilet': ['toilet', 'toalet', 'wc', 'w.c', 'klo', 'toilette', 'gabinett', 'water', 'inodor', 'retrete', 'sanita', 'vaso', 'toalett', 'toilett', 'istuin', 'istuim', 'vessa', 'tualet',
               'klozet', 'záchod', 'zachod', 'stranišč', 'školjk', 'wc-', 'vécé', 'toaletă', 'тоалет', 'унитаз', 'туалет', 'τουαλέτ', 'λεκάν', 'tuvalet', 'klozet', 'salernó'],
    'basin': ['washbasin', 'wash basin', 'basin', 'lavabo', 'lavabi', 'lavandino', 'waschbecken', 'waschtisch', 'lavatory', 'lavatories', 'lavatório', 'wastafel',
              'tvättställ', 'servant', 'håndvask', 'pesuallas', 'pesualta', 'kraanikauss', 'umywalk', 'umyvadl', 'umývadl', 'umivaln', 'mosdó', 'chiuvet', 'мивк', 'умывальник',
              'νιπτήρ', 'izlietn', 'praustuv'],
    'sink': ['sink', 'allas', 'altaa', 'altai', 'spüle', 'evier', 'évier', 'lavello', 'fregadero', 'pia ', 'gootsteen', 'diskbänk', 'vask', 'zlewozmywak', 'dřez', 'mosogat', 'мойк'],
    'bathtub': ['bathtub', 'bath tub', 'tub', 'badewanne', 'wanne', 'baignoire', 'vasca', 'vasche', 'bañera', 'banheira', 'badkuip', 'badkar', 'badekar', 'kylpyamme', 'amme',
                'vann ', 'vanni', 'wanna', 'wanny', 'van', 'kád', 'cadă', 'căzi', 'cazi', 'вана', 'ванн', 'μπανιέρ', 'küvet', 'vonia', 'vanna'],
    'shower': ['shower', 'dusch', 'douche', 'doccia', 'docce', 'ducha', 'chuveiro', 'duche', 'dusj', 'bruse', 'suihku', 'dušš', 'duša', 'dušas', 'prysznic', 'sprch', 'tuš', 'zuhany',
               'duș', 'душ', 'ντουζ', 'duş', 'sturta'],
    'apartment': ['apartment', 'flat', 'wohnung', 'appartement', 'appartament', 'apartamento', 'piso', 'lägenhet', 'leilighet', 'lejlighed', 'huoneisto', 'asunto', 'asunno',
                  'korter', 'dzīvokl', 'butas', 'butų', 'mieszkan', 'byt', 'bytu', 'stanovanj', 'stan ', 'stanova', 'lakás', 'apartament', 'апартамент', 'квартир', 'стан',
                  'διαμέρισμ', 'daire', 'íbúð', 'árasán', 'residential unit', 'units', 'whg', 'app.'],
    'room': ['room', 'raum', 'räume', 'zimmer', 'pièce', 'piece', 'locale', 'locali', 'stanza', 'habitación', 'cuarto', 'quarto', 'divisão', 'kamer', 'ruimte', 'rum', 'rom',
             'huone', 'tila', 'ruum', 'ruumi', 'telp', 'istab', 'kambar', 'patalp', 'pokój', 'pokoj', 'pomieszcz', 'místnost', 'miestnost', 'prostor', 'soba', 'helyiség', 'szoba',
             'cameră', 'încăper', 'стая', 'помещ', 'комнат', 'просторија', 'δωμάτι', 'χώρ', 'oda', 'herbergi', 'seomra', 'space', 'spaces', 'locaux'],
    'wall': ['wall', 'wand', 'wände', 'mur', 'muro', 'muri', 'parede', 'pared', 'muur', 'vägg', 'vegg', 'væg', 'vægge', 'sein', 'sien', 'siena', 'ściana', 'ścian', 'stěn', 'stena',
             'sten', 'zid', 'fal', 'perete', 'pereț', 'стен', 'τοίχ', 'duvar', 'veggur', 'balla'],
    'column': ['column', 'stütze', 'säule', 'poteau', 'colonn', 'pilar', 'columna', 'kolom', 'pelare', 'søyle', 'søjle', 'pilari', 'post', 'kolonn', 'kolumn', 'sloup', 'stĺp',
               'steber', 'stup', 'oszlop', 'stâlp', 'колон', 'κολόν', 'kolon'],
    'beam': ['beam', 'träger', 'balken', 'poutre', 'trave', 'viga', 'balk', 'balkar', 'bjelke', 'bjælke', 'palk', 'sija', 'palkk', 'belka', 'nosník', 'nosnik', 'gred', 'greda',
             'gerenda', 'grind', 'грed', 'балк', 'δοκ', 'kiriş', 'kiris'],
    'stair': ['stair', 'treppe', 'escalier', 'scala', 'scale', 'escalera', 'escada', 'trap', 'trapp', 'trappe', 'portaa', 'portai', 'trepp', 'kāpn', 'laipt', 'schod', 'stopni',
              'stepeni', 'lépcső', 'scar', 'стълб', 'лестниц', 'степени', 'σκάλ', 'merdiven', 'stigi'],
    'slab': ['slab', 'decke', 'platte', 'dalle', 'solaio', 'solai', 'losa', 'laje', 'vloer', 'bjälklag', 'dekke', 'dæk', 'laatta', 'laata', 'plaat', 'pāršeg', 'perdang', 'strop',
             'płyt', 'deska', 'ploča', 'födém', 'placă', 'плоч', 'плит', 'πλάκ', 'döşeme', 'plötu'],
    'sanitary': ['sanitary', 'sanitär', 'sanitaire', 'sanitari', 'sanitario', 'sanitár', 'sanitet', 'saniteet', 'sanitaar', 'sanitar', 'санитар', 'υγιειν', 'fixture'],
    'kitchen': ['kitchen', 'küche', 'cuisine', 'cucina', 'cocina', 'cozinha', 'keuken', 'kök', 'kjøkken', 'køkken', 'keittiö', 'keitti', 'keittokomero', 'köök', 'virtuv', 'kuchn',
                'kuchyň', 'kuchyn', 'kuhinj', 'konyha', 'bucătări', 'кухн', 'κουζίν', 'mutfak', 'eldhús', 'cistin'],
    'bedroom': ['bedroom', 'makuuhuone', 'makuuhuonet', 'schlafzimmer', 'chambre', 'camera da letto', 'dormitorio', 'quarto de dormir', 'slaapkamer', 'sovrum', 'soverom',
                'soveværelse', 'magamistuba', 'guļamistab', 'miegamas', 'sypialn', 'ložnic', 'spálň', 'spavaća', 'hálószob', 'dormitor', 'спалн', 'спальн', 'υπνοδωμάτι', 'yatak odası'],
    'bathroom': ['bathroom', 'washroom', 'kylpyhuone', 'kylpy- tai pesuhuone', 'pesuhuone', 'badezimmer', 'bad ', 'salle de bain', 'bagno', 'baño', 'casa de banho', 'badkamer',
                 'badrum', 'baderom', 'badeværelse', 'vannituba', 'pesuruum', 'vannas istaba', 'vonios', 'łazienk', 'koupeln', 'kúpeľň', 'kupaonic', 'kopalnic', 'fürdőszob',
                 'baie', 'баня', 'ванная', 'μπάνι', 'banyo'],
    'balcony': ['balcon', 'balkon', 'balcony', 'parveke', 'parvekk', 'balcone', 'balcón', 'varanda', 'altan', 'altaan', 'rõdu', 'balkōn', 'balkons', 'balkonas', 'balkón', 'erkély',
                'балкон', 'μπαλκόν', 'loggia', 'terrace'],
    'sauna': ['sauna', 'saun', 'löyly', 'sauno', 'сауна', 'σάουνα', 'pirts'],
    'storey': ['floors (storeys)', 'storey', 'storeys', 'stories', 'kerros', 'kerrost', 'geschoss', 'stockwerk', 'étage', 'piano', 'planta', 'andar', 'verdieping', 'våning', 'etasje',
               'etage', 'korrus', 'stāv', 'aukšt', 'kondygnac', 'piętr', 'podlaž', 'poschod', 'nadstrop', 'kat ', 'emelet', 'etaj', 'етаж', 'этаж', 'όροφ', 'hæð'],
    'area': ['area', 'm²', 'm2', 'sqm', 'fläche', 'surface', 'superficie', 'oppervlak', 'yta', 'areal', 'ala ', 'pinta-ala', 'pindala', 'pind', 'platība', 'plotas', 'powierzchn',
             'plocha', 'ploch', 'površin', 'terület', 'suprafaț', 'suprafat', 'площ', 'επιφάνει', 'εμβαδ', 'alan', 'flatarmál'],
    'volume': ['volume', 'volumen', 'volum', 'm³', 'm3', 'rumfang', 'tilavuus', 'maht', 'tilavuu', 'objętość', 'objem', 'prostornin', 'térfogat', 'обем', 'объём', 'объем', 'όγκ',
               'hacim', 'rúmmál', 'tūrīs', 'tūris'],
    'length': ['length', 'länge', 'longueur', 'lunghezza', 'longitud', 'comprimento', 'lengte', 'längd', 'lengde', 'længde', 'pituus', 'pikkus', 'garums', 'ilgis', 'długość',
               'délka', 'dĺžka', 'dolžin', 'duljin', 'hossz', 'lungime', 'дължин', 'длин', 'μήκ', 'uzunluk', 'lengd', 'metres', 'metros', 'meter'],
    'side_area': ['side area', 'seitenfläche', 'sideareal', 'külgpind', 'surface latérale', 'superficie laterale', 'sivupinta', 'wall area', 'netsidearea'],
    'labelled': ['labelled', 'labeled', 'bezeichnung', 'bezeichnet', 'désignation', 'désignées', 'intitul', 'denominazione', 'denominati', 'etichett', 'nimetty', 'nimellä',
                 'märgistatud', 'nimega', 'oznaczon', 'označen', 'denumit', 'обозначен', 'με την ονομασία', 'etiketli', 'named'],
    'numbered': ['numbered', 'nummerierten', 'nummeriert', 'numérotées', 'numerati', 'numerad', 'numerowan', 'číslovan', 'numerotat', 'нумерован', 'αριθμημέν', 'numaralı',
                 'interni', 'intérieures', 'indoor', 'innen', 'sisä'],
}

def fold(s):
    """lowercase + strip diacritics (é->e, ά->α, ă->a) so stems match any accentuation"""
    s = unicodedata.normalize('NFD', s.lower().replace('ß', 'ss').replace('ł', 'l').replace('ø', 'o').replace('æ', 'ae'))
    return ''.join(ch for ch in s if unicodedata.category(ch) != 'Mn')


def norm(s):
    return ' ' + re.sub(r'\s+', ' ', fold(s)) + ' '


@functools.lru_cache(maxsize=None)
def _rx(concept):
    stems = sorted({fold(x) for x in LEX[concept]}, key=len, reverse=True)
    return re.compile(r'(?<![a-zа-яα-ω])(?:' + '|'.join(re.escape(x) for x in stems) + ')', re.I)


def has(concept, text):
    t = norm(text)
    return bool(_rx(concept).search(t))


def first(text, concepts):
    """Earliest-mentioned concept among `concepts` (questions name their object early)."""
    t = norm(text)
    best = None
    for c in concepts:
        m = _rx(c).search(t)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), c)
    return best[1] if best else None
