# Porkbun (.com registrar) kurulumu

`.com` tarafinda kayit Porkbun API v3 uzerinden yapilir.
Resmi dokumantasyon: <https://porkbun.com/api/json/v3/documentation>

## 1. Hesap ve API erisimi

1. Porkbun hesabi acin, 2FA'yi etkinlestirin.
2. Account -> API Access bolumunden **API Key** ve **Secret API Key** olusturun.
3. Kayit yapacaginiz hesapta **kredi** bulundurun. `domain/create` yalnizca hesap
   bakiyesinden duser; kart cekmez. Bakiye yoksa dry-run `sufficientFunds: false` doner.

`.env`:

```
PORKBUN_ENABLED=true
PORKBUN_API_KEY=pk1_...
PORKBUN_SECRET_API_KEY=sk1_...
```

## 2. Baglanti testi

```bash
python3 -m app.cli ping
```

Cikti `credentialsValid: true` ve cagiran IP'yi icermeli.

## 3. Kullanilan endpoint'ler

| Endpoint | Amac | Limit (varsayilan) |
|---|---|---|
| `POST /ping` | Kimlik ve IP dogrulama | — |
| `POST /domain/checkDomain/{domain}` | Musaitlik + fiyat | 10 saniyede 1 sorgu / hesap |
| `POST /domain/create/{domain}` | Kayit (`dryRun` destekli) | 10 saniyede 1 deneme; 24 saatte 50 basarili kayit |
| `POST /domain/listAll` | Kayit sonrasi dogrulama | — |

Bu yuzden **surekli izleme Porkbun ile degil RDAP ile yapilir**; Porkbun yalnizca
satin alma anında devreye girer.

## 4. Fiyat ve `cost` alani

`domain/create` cagrisinda `cost` **kurus (penny) cinsinden** ve o anki fiyatla
**birebir ayni** olmalidir. Bu yuzden akis su sekildedir:

```
checkDomain -> price ("11.06") -> price_cents (1106) -> create(cost=1106)
```

Fiyat okunamazsa veya `MAX_REGISTRATION_COST_USD` tavanini asarsa kayit yapilmaz (G7).

## 5. Dry-run

`REGISTER_DRY_RUN_FIRST=true` iken her canli kayittan once `dryRun: true` ile
prova yapilir. Prova `wouldSucceed: false` veya `sufficientFunds: false` donerse
canli istek gonderilmez (G8).

```bash
python3 -m app.cli dry-run ornek.com
```

## 6. Drop-catch gercekci beklenti

Yuksek talepli bir `.com` domain drop aninda saniyeler icinde kapilir; registry
baglanti kapasitesi yuksek profesyonel drop-catch servisleri avantajlidir.
Bu depo:

- lifecycle takibi + anlik uyari,
- drop aninda tek registrar uzerinden hizli deneme

saglar. Domain sizin icin gercekten degerliyse paralel olarak backorder/drop-catch
servisi kullanin. Bu depo onlarin yerine gecmez.
