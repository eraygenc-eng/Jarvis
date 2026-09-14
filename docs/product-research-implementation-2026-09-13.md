Jarvis ürün araştırması — mantık, kod ve doğrulama kaydı

Başlangıç commit'i: `b3e45ed`. İstek: aynı kaynak kapsamıyla doğru ürün/satıcı teklifini doğrulamak, bağlantıları kullanıcıya ulaştırmak ve yapılan düzeltmeleri önemli kodlarıyla açıklamak. Bu dosya ilk somut hedefin uygulama kaydıdır; genel incelemedeki bütün geliştirmelerin tamamlandığı anlamına gelmez.

“Neyi yanlış yapmışım?” sorusunu önceki kodun varsayımları üzerinden açıklıyorum. Kodun bir bölümünü önceki görüşmelerde ben önermiş olabilirim; kişiye hata atfetmek yerine, eski davranışı ve yerine gelen kontrolü gösteriyorum. Aşağıdaki önce/sonra parçaları ilgili işleyişi göstermek için kısaltılmıştır. Tam uygulama bağlantıları her maddede bulunur.

**1. Modele hem kanıtı yazdırmak hem sayıyı dönüştürtmek**

Eski yaklaşımda modelin doğru ürünü bulması yetmiyordu. Sayfadaki metni birebir kopyalaması, doğru fiyat düğümünü yazması, sayıyı ayıklaması, ondalık ayırıcıyı seçmesi ve satıcıyı doğru adlandırması gerekiyordu. Bunların hepsi büyük bir `OfferQuote` içinde bekleniyordu:

```python
def research_verify_result(result_id, observation_id, quote: OfferQuote):
    observation = observation_store.require_current(observation_id)
    validate_quote(state, result, observation, quote)
    apply_quote(result, observation, quote)
```

Son eski logda model bunun yerine şu tür bir açıklama göndermişti:

```python
{
    "identity_evidence": "Heading identifies Logitech G Pro X Superlight 2 ...",
    "price_evidence": "Current payable price shown as 6.989 TL ...",
    "price_amount_texts": {"price": "6.989 TL"},
    "price_decimal_separator": ".",
}
```

Bu bir kanıt alıntısı değildi; tutar alanına para birimi eklenmişti, Türkçe binlik ayırıcı yanlış yorumlanmıştı ve fiyatın referansı yoktu. Aynı işlemi tekrar denemek aynı sınıftaki hataları çoğalttı.

Yeni ürün aracı modelden **hangi düğümlerin seçileceğini** istiyor:

```python
selection = ProductQuoteSelection(
    offer_ref="f12e83",
    identity_ref="f12e84",
    seller_ref="f12e96",
    seller="GamingGenTR",
    price_ref="f12e143",
    currency="TRY",
    decimal_separator=",",
    quantity_ref="f12e136",
    shipping_ref="f12e110",
)
```

Python gerçek metinleri gözlemden okuyor ve sayıyı çıkarıyor:

```python
index = SnapshotIndex(
    SnapshotIndex(observation.page_text).read(selection.offer_ref)
)
identity = index.read(selection.identity_ref)
seller = index.read(selection.seller_ref)
price = index.read(selection.price_ref)
token, amount = read_amount(
    price, selection.decimal_separator, selection.amount_text
)
```

`read_amount` önce snapshot referanslarını ve URL'leri çıkarır; böylece `ref=e123` içindeki 123 fiyat olamaz. `Decimal` ile dönüşüm yapar ve mevcut `validate_observed_amount` üzerinden sayının gerçekten seçilen metinde bulunduğunu kontrol eder. Belirsiz birden çok sayı varsa modelden daha dar fiyat düğümü veya yalnızca sayısal `amount_text` ister. “6.989 TL” için doğru sonuç 6989'dur; “.” ayırıcısıyla yanlışlıkla 6,989 kabul edilmez.

Yeni yol hâlâ aynı `validate_quote` ve `apply_quote` işlevlerine ulaşır. Ayrı bir doğrulama kestirmesi veya siteye özel fiyat sabiti eklenmedi. Diğer kategorilerde eski quote aracı korunuyor.

Kod: [product_quote.py](../core/research/product_quote.py), [quote_evidence.py](../core/research/quote_evidence.py), [research_tools.py](../core/research/research_tools.py).

**2. “Aynı büyük bölgede bulunuyor” ile “aynı teklife ait” ayrımı**

Eski kodun önemli kontrolü şuydu:

```python
scope = get_snapshot_subtree(observation.page_text, quote.offer_ref)
identity = _excerpt(scope, quote.identity_evidence, "Identity evidence")
seller_evidence = _excerpt(scope, quote.seller_evidence, "Seller/provider evidence")
evidence = _excerpt(scope, quote.price_evidence, "Price evidence")
```

Kök sayfa bölümü seçildiğinde iki ürün veya iki satıcı bu aynı `scope` içine girebiliyordu. Metinlerin ayrı ayrı bulunması fiyatın doğru satıcıya ait olduğunu ispatlamıyordu.

Yeni kontrol snapshot girintilerinden ebeveyn/çocuk ilişkisini kuruyor. Fiyatın bulunduğu bağımsız başlıklı kart, başka karttaki ürün kimliğiyle birleştirilemiyor. Satıcı bağlantısı ve satın alma alanı olan ayrı bir kartın fiyatı da başka satıcıya taşınamıyor:

```python
validate_relationships(scope, identity, seller_evidence, evidence)

# Fiyatın atalarında bağımsız bir ürün başlığı varsa:
if has_heading and not contains(ancestor, identity_node):
    raise ValueError("Price and identity belong to different offer containers.")

# Ayrı satıcı/satın alma alanının fiyatını başka satıcıya bağlama:
if has_purchase and navigable_links and not contains(ancestor, seller_node):
    raise ValueError("Price and seller belong to different offer containers.")
```

Satıcı adı artık bütün sayfa bölgesinde değil, seçilen satıcı kanıtında aranıyor. Gerçek Koçtaş fixture'ında GamingGenTR'nin 6.989 TL fiyatı kabul edilirken Jetklik'in 8.703,28 TL fiyatını GamingGenTR'ye bağlayan senaryo reddediliyor. Bir başka test, kardeş ürün kartındaki 100 TL'nin ilk ürüne taşınmasını engelliyor.

Bu kontrol bilinen yapısal belirsizlikleri reddeder; bütün sitelerin semantik düzenini eksiksiz çözen genel bir DOM yorumlayıcısı değildir. Yeni bir düzen belirsizse kanıtı genişleterek zorla kabul ettirmek yerine yeni örnek/test ve dar bir kontrol eklenmelidir.

Kod: [quote_evidence.py](../core/research/quote_evidence.py), [offer_verification.py](../core/research/offer_verification.py).

**3. Ürün adedi ve bilinmeyen kargo**

Eski state `criteria={}` ile oluşuyordu. Ürünlerde `price_scope='total'` için kapsam alıntısı zorunlu değildi. Yeni planlama açık sayısal adet isteklerini tutuyor:

```python
def product_criteria(prompt: str) -> dict:
    match = re.search(
        r"\b(\d+)\s*(?:adet|tane|items?|units?|pieces?)\b", prompt, re.I
    )
    return {"quantity": int(match[1]) if match else 1}
```

Ürün doğrulamasında seçilen adet ile talep karşılaştırılıyor:

```python
requested = state.criteria.get("quantity", 1)
if quantity_evidence and quantity != requested:
    raise ValueError("Selected quantity does not match requested quantity ...")
scope = "total" if quantity == requested == 1 else "unit"
```

Bu ilk teslim tek adet ürünün doğrulanmış toplamını hedefliyor. Adet kanıtı olmayan tutar birim fiyat olarak kalıyor. Çok adetli istekte sayfa üzerindeki tek ürün fiyatı otomatik çarpılıp doğrulanmış sipariş toplamı yapılmıyor. Yazıyla ifade edilen her dildeki adetleri çözmek ve seyahat koşullarını yapılandırmak bu teslimin tamamladığı işler değil.

Kargo bilinmiyorsa `shipping_cost=None` kalıyor. Ücretsiz kargo ancak ilgili düğümde açık bir ifade varsa kullanılıyor; üyelik veya alt limit içeren ifade otomatik sıfır kargo sayılmıyor. Ayrıca rastgele bir satıcı adı artık “bütün zorunlu ücretler dahil” kanıtı olarak kabul edilmiyor.

Kod: [research_manager.py](../core/research/research_manager.py), [product_quote.py](../core/research/product_quote.py), [offer_verification.py](../core/research/offer_verification.py).

**4. Kaynak kapsamını metinsel beyana bırakmak**

Eskiden üç farklı sorgu cümlesi kaydetmek üç gerçek aramaya eşdeğerdi:

```python
added = source_state.record_discovery_attempt(query=query, note=note)
# Sonra discovery_attempt_count() >= 3 ise NO_RESULTS mümkün oluyordu.
```

Yeni araç gerçek gözlem kimliği istiyor. Doğrudan kaynaklarda kanıtın o kaynağın domain'inde olması gerekiyor. Aynı sayfayı yeni gözlem kimliğiyle tekrar saymayı da içerik özeti engelliyor:

```python
observation = source_evidence(canonical_source, observation_id)
fingerprint = hashlib.sha256(
    (observation.page_url + "\n" + visible_text(observation.page_text)).encode()
).hexdigest()
if any(item["fingerprint"] == fingerprint
       for item in source_state.discovery_evidence):
    return "DISCOVERY ATTEMPT NOT COUNTED: ..."
```

Kayıt query + observation ID + URL + fingerprint taşır. `research_add_result` da keşif gözlemini saklar. Kaynak engeli ve teklif engeli için gerçek sayfa/hata kaydından alıntı istenir. “Kanıt formatını yanlış verdim” bir site engeli değildir; doğru referansla yeniden denenmeli veya araştırma kısmi kalmalıdır.

Snapshot referansları değişse bile aynı URL ve aynı görünür içerik tekrar sayılmaz. CAPTCHA, 403 ve sayfa erişim hataları boş ürün araması sayılmaz. Keşif kaydında eşleşen bir ürün başlığı görülmüşse, teklif ekleme çağrısının reddedilmesi `NO_RESULTS` gerekçesi olamaz.

MCP'nin gerçek navigasyon hatası da saklanır:

```python
if response.isError and url.startswith(("http://", "https://")):
    observation = self.observations.capture(url, text, kind="error")
    # Araç yanıtına gerçek hatanın Observation ID'si eklenir.
```

`require_current` bu `kind='error'` kaydının fiyat doğrulamasında kullanılmasını reddeder. Arama kaydı için arşivdeki gerçek gözlem kullanılabilir; arşiv okumak gözlemi yeniden güncel yapmaz. Üç farklı sayfa gözlemi bütün internetin tarandığını ispatlamaz; raporda yalnızca kayıtlı kapsam gösterilir.

Kod: [evidence.py](../core/research/evidence.py), [browser.py](../core/tools/browser.py), [comparison_state.py](../core/research/comparison_state.py), [research_tools.py](../core/research/research_tools.py).

**5. Nihai bağlantıları modelin hatırlamasına bırakmak**

Eskiden URL'ler model girdisindeydi ama son cevap doğrudan modelden dönüyordu:

```python
report = extract_response_text(response.content)
return report
```

Yeni akış araçsız tek rapor çağrısını koruyor, modelden kısa açıklama istiyor ve zorunlu tabloyu Python ile ekliyor:

```python
self._refresh_final_page_status()
report = extract_response_text(response.content) + "\n\n" + render_report_table(
    self.current_comparison_state, prompt
)
```

Tablo bütün planlı kaynakları, kanıt bağlantılarını, bütün teklifleri, satıcıyı, para birimini, fiyatı, toplam durumunu, doğrulama durumunu, teklif ve keşif URL'sini içerir. Koşullu fiyatlar ve fiyat geçmişi ayrıca korunur. URL'ler yalnızca HTTP(S) ise bağlantı yapılır; sayfa başlıklarındaki tablo/Markdown karakterleri kaçırılır. Araştırma hazır değilse tablo “kısmi” der.

Kod: [report.py](../core/research/report.py), [agent.py](../core/agent.py).

**6. Tekrarlar, son kontrol ve ölçümün tekrar üretilebilmesi**

Tam aynı kaynak/teklif/veri/gözlem tekrar eklenirse aynı ID döner. Farklı kaynak, satıcı veya değişen fiyat birleştirilmez. Aynı offer URL'sini tekrar vermek final kararı bozmaz; URL gerçekten değişirse doğrulama ve final kararı sıfırlanır.

Ürün doğrulama aracı `final_check=True` ile mevcut son kontrol çekirdeğini çağırır:

```python
quote = build_product_quote(state, observation, selection)
if final_check:
    return confirm_final_page(result_id, observation_id, quote)
return verify_result(result_id, observation_id, quote)
```

İçeride decorated tool'u yeniden `invoke` etmek yerine ortak Python fonksiyonları kullanılır. Böylece sahte iç içe araç ölçümü yaratılmaz. Son kontrolde yeni snapshot şartı, fiyat değişince sıralamanın açılması ve güncel gözlem kontrolü korunur.

MCP sürümü bu bilgisayarda kurulu ve incelenmiş `0.0.80` sürümüne sabitlendi. Model/sağlayıcı değiştirilmedi. Yeni kabul komutu aynı yedi kaynakla gerçek bir koşu yapıp `report.md`, `state.json`, `observations.json` ve `summary.json` üretir:

```powershell
.\.venv\Scripts\python.exe -X utf8 -u -B -m scripts.research_acceptance
```

Bu komut gerçek API ve tarayıcı isteği yapar. Çıktılar `artifacts/acceptance-.../` altına yazılır; `artifacts/` Git'ten dışlanmıştır. Etkileşimsiz testte onay gerektiren eylemler yürütülmez. Araştırma varsayılan olarak 900 saniyede sınırlandırılır; sınırda kayıtlar korunur ve başarısız kabul sonucu yazılır.

Varsayılan tarayıcı `main.py` ile aynı şekilde görünür açılır; isteğe bağlı `--headless` vardır. Koşu başlamadan `core/`, `config/` ve `scripts/` altındaki Python dosyalarının SHA-256 özetleri alınır. Böylece Git'e henüz eklenmemiş yeni uygulama dosyaları da çalıştırılan sürümün kaydına girer. API anahtarları bu kayda alınmaz.

Kabul koşulu yalnızca “program bitti” değildir:

```python
passed = (
    ready
    and verified_offers > 0
    and final_page_verified
    and error is None
)
```

Kod: [research_acceptance.py](../scripts/research_acceptance.py), [research_tools.py](../core/research/research_tools.py), [context.py](../core/context.py), [security/middleware.py](../core/security/middleware.py).

**7. Canlı testte kendi ilk uygulamamda bulduğum iki hata**

İlk ağ erişimli koşu 425,50 saniye, 110 model çağrısı ve **0 doğrulanmış teklifle** bitti. Bu başarısız bir kabul koşusudur. İki sorun, ilk eklediğim keşif kanıtı kontrolündeydi; bunları kullanıcının eski koduna atfetmiyorum.

İlki, tek bir aday başlığını değerlendirmek için yazılmış kimlik kontrolünü bütün snapshot üzerinde çağırmamdı:

```python
# İlk uygulamadaki hata:
get_product_identity_conflict(state.target_product, discovery.page_text)
```

İtopya sayfasının ana başlığı standart Superlight 2 olmasına rağmen aşağıdaki tanıtım görsellerinin alt metninde `Superlight 2 DEX` vardı. Bütün sayfa tek ürün kimliği gibi değerlendirilince doğru ürün yedi kez reddedildi. Yeni yaklaşım her başlık/bağlantıyı ayrı aday olarak okur; kayıt için verilen başlığın da o adayla uyuşmasını ister:

```python
candidates = [visible_text(index.text(node)) for node in index.nodes
              if re.search(r"- (?:heading|link)\b", node.line)]
return any(
    get_product_identity_conflict(target, candidate) is None
    and get_product_identity_conflict(title, candidate) is None
    for candidate in candidates
)
```

Tam kod ayrıca arama sonucu başlıklarını ayırır. Google Shopping bazı başlıkları `generic` metni veya YAML içinde tırnaklı `button` olarak veriyor; bu düğümlerin kendi satırı da desteklenir. Generic bir bölgenin bütün alt elemanları birleştirilmez: ayrı kartlardan `Logitech Superlight` ve `2` parçaları toplanamaz. Bu yalnızca keşif kontrolüdür; satıcı ve fiyat yine taze teklif sayfasında doğrulanır. DEX başlığından standart model üretmek ve beyaz başlık yokken beyaz teklif kaydetmek kabul edilmez.

İkinci hata, gerçek gözlem kimliğinin tek başına başarılı arama kanıtı sayılmasıydı. Model üç ayrı CAPTCHA sayfası gördükten sonra kaynağı `no_results` olarak kapatabiliyordu. Artık erişim engelinin gerçek satırı ayrılır:

```python
failure = access_failure_excerpt(observation)
if failure:
    return (
        "DISCOVERY ATTEMPT NOT COUNTED: The page is unavailable, "
        "not an empty search. ... copied observed_evidence: " + failure
    )
```

Model aynı hatayı açıklama cümlesi olarak yeniden yazmak zorunda kalmaz; araç doğru alıntıyı verir. Kaynak kapatılırken arşiv kanıtları da yeniden denetlenir. Uydurulan arama URL'si 404 verirse ana sayfadaki gerçek arama alanı kullanılmalıdır; prompt bunu açıkça söyler. Gerçekten boş dönen üç farklı arama hâlâ `NO_RESULTS` ile bitebilir. Dört yeni regresyon testi bu ayrımı, başlık karışmasını ve bulunan ürünü yok saymayı kapsar.

Kod: [discovery_evidence.py](../core/research/discovery_evidence.py), [research_tools.py](../core/research/research_tools.py), [prompts.py](../core/prompts.py), [test_product_acceptance.py](../tests/test_product_acceptance.py).

**8. Yanlış hata mesajı ve keşifteki mağaza etiketi**

İkinci ağ erişimli koşu, var olan satıcı referansının seçilen dar teklif bölümü dışında kalması nedeniyle tekrarlandı. Eski mesaj `Unknown snapshot reference` diyordu; model aynı referanslarla yeni snapshot alıyordu. Referans aslında bütün sayfada vardı. Yeni kod önce tam sayfada referansları bulur, sonra kapsamı kontrol eder ve seçilen kanıtların ortak üst bölümünü döndürür:

```python
outside = [node for node in selected_nodes if not contains(scope_node, node)]
if outside:
    common = selected_nodes[0]
    while common and not all(contains(common, node) for node in selected_nodes):
        common = common.parent
    # "outside offer_ref ... Common container: f49e3"
    # Aynı seçimle tekrar snapshot almak kapsam hatasını düzeltmez.
```

Kapsam kendiliğinden genişletilip teklif kabul edilmez; model önerilen üst bölümü seçse bile satıcı/fiyat ilişki kontrolleri yine çalışır. Yeni test hem doğru üst bölüm önerisini hem doğrulamanın henüz yapılmadığını kontrol eder.

Üçüncü koşuda gerçek Koçtaş sayfasındaki GamingGenTR teklifi doğrulandı. Fakat Google kartından alınan `seller='Koçtaş'` etiketi başka bir bekleyen kayıt olarak kalabiliyordu. Burada mağaza/platform adı ile asıl satıcı birbirine karışıyordu.

Yeni kural ürünlerde yalnızca **daha önce hiç doğrulanmamış**, adı ziyaret edilen domain'in bir etiketiyle tam eşleşen keşif mağazasının gerçek satıcıya dönüşmesine izin verir. Türkçe karakterler domain karşılaştırması için normalize edilir:

```python
if any(entry.get("stage") == "verified" for entry in result.price_history):
    return False
seller = domain_label(result.seller or "")
host_labels = (urlsplit(page_url).hostname or "").split(".")
return len(seller) >= 4 and any(seller == domain_label(label) for label in host_labels)
```

Bu izin yalnızca satıcı etiketi farkını açıklar; yeni satıcının adı, ürün kimliği, fiyat düğümü ve diğer kanıtları yine tam doğrulamadan geçer. `Jetklik → GamingGenTR` gibi iki gerçek satıcı değişimi ve daha önce doğrulanmış bir satıcının değişmesi reddedilir. İlk keşifteki `Koçtaş` değeri fiyat geçmişinde ve `details['discovery_seller_label']` içinde kalır; rapor `Koçtaş → GamingGenTR` dönüşümünü ayrıca gösterir. Seyahat akışının satıcı kuralı değiştirilmez.

Kod: [product_quote.py](../core/research/product_quote.py), [offer_verification.py](../core/research/offer_verification.py), [report.py](../core/research/report.py).

**Doğrulama kaydı**

- Başlangıçtaki 59 teste 18 kabul/regresyon testi eklendi; toplam **77 test geçti**. Kayıt: `artifacts/unit-tests-final.log`.
- Gerçek arşiv sayfası: doğru satıcı/fiyat/ücretsiz kargo ve tek adet kanıtı kabul edildi.
- Yanlış satıcı fiyatı ve kardeş ürün kartı fiyatı reddedildi.
- Yanlış adet, bilinmeyen kargo, yanlış sayı biçimi ve ilgisiz ücret alıntısı kontrol edildi.
- Gerçek gözlem olmadan kaynak kapatma ve aynı sayfayı tekrar arama sayma reddedildi.
- Yedi kaynaklı kontrollü senaryo, yeni son snapshot ve bütün kaynak/teklif bağlantılarıyla tamamlandı. Diğer kaynaklardaki engeller bu testte yapay veridir; canlı site başarısı olarak sunulmaz.
- İlk canlı deneme MCP başlangıcında npm `EACCES` hatasıyla durdu; **0 model çağrısı**. Kayıt: `artifacts/acceptance-20260913T152451Z/summary.json`.
- İlk ağ erişimli deneme: `artifacts/acceptance-20260913T153014Z/summary.json`. Headless tarayıcı, 425,50 saniye, 110 model çağrısı, 1.735.669 giriş tokenı, 11.498 çıkış tokenı; **kabul başarısız**. `ready=True` tek başına başarı değildir: 0 doğrulanmış teklif ve son sayfa kontrolü yok. Bu koşudaki yanlış kaynak durumları 7. maddede düzeltilmiştir.
- İkinci ağ erişimli deneme tekrar eden kapsam hatası yüzünden tarafımdan durduruldu: `artifacts/acceptance-live-v2-interruption.json`. 140 tamamlanmış model çağrısı, 0 doğrulanmış teklif. Bu eski koşuda tam state kapanış kaydı yok; konsol kaydı korunuyor. Bu koşu başarılı veya tam kapsamlı sayılmıyor.
- Üçüncü ağ erişimli deneme: `artifacts/acceptance-20260913T155156Z/summary.json`. 298,89 saniye ve 69 model çağrısı. Aynı GamingGenTR teklifine ait **2 doğrulanmış kayıt, 1 benzersiz teklif** elde edildi: Koçtaş ürün sayfasında tek adet, 6.989 TL ve ücretsiz kargo. Keşif mağaza etiketi sorunu nedeniyle kaynak kapsamı tamamlanmadı ve son sayfa onayı yapılmadı; `passed=False`. `STOP` dosyasıyla kontrollü durduruldu, `state.json`, `observations.json` ve kısmi `report.md` korundu.
- Son satıcı etiketi düzeltmesiyle uygulamayla aynı görünür tarayıcı, aynı model ve aynı yedi kaynakla canlı kabul yeniden çalıştırılıyor; nihai sonuç burada kaydedilecek. Headless/görünür tarayıcı farkı ve değişen site sonuçları nedeniyle bu koşular tek başına hız kazanımı yüzdesi olarak karşılaştırılamaz.

Genel incelemedeki seyahat kapsamı, görev değiştirme/iptal, tüm güvenlik kararları, sağlayıcılar arası araç uyumu, kalıcı bellek ve CI gibi başlıklar bu ürün hedefinden ayrı kalan işlerdir. Bu kayıt onların çözüldüğü iddiasını taşımaz.
