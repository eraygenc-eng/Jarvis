Jarvis performans çalışması — uygulama ve devir planı

Hazırlanma tarihi: 10 Eylül 2026. İncelenen commit: `217b43e`.
Durum: Plan hazır. Performans değişiklikleri henüz uygulanmadı.

13 Eylül 2026 güncellemesi: Yukarıdaki durum 10 Eylül başlangıcını anlatır. A1/A2/B/C1/C2 güncel kodda mevcut. Kullanıcı ilk somut ürün doğrulama hedefinin uygulanmasını açıkça istedi; bu teslimin mantık, önce/sonra kod ve test kaydı [product-research-implementation-2026-09-13.md](product-research-implementation-2026-09-13.md) dosyasındadır. Güncel genel inceleme [project-review-2026-09-13.md](project-review-2026-09-13.md) dosyasındadır. Sonraki çalışma eski A1 bekleme kaydından yeniden başlatılmamalıdır.

**Sonraki model önce burayı okusun**

Kullanıcı değişiklikleri öğrenerek, kendisi yapmak istiyor. Her yanıtta yalnızca sıradaki küçük adımı anlat: hangi dosya, hangi fonksiyon, eklenecek/çıkarılacak kod, nedeni ve nasıl kontrol edileceği. Kullanıcı açıkça uygulamanı istemedikçe uygulama kodunu sen değiştirme. Bu dosyanın hazırlanması bütün adımların topluca uygulanmasına izin değildir.

Kullanıcının hedefi belirlediği kaynaklarda her türlü ürün, uçuş, otel ve araç kiralama araştırmasının doğru ve hızlı çalışması. Logitech/Akakçe için özel fiyat kestirmesi yazma. Son ürün denemesinde bütün fiyatların doğru olduğunu, araştırmanın çok yavaş olduğunu bildirdi. Önceki görüşmede yaklaşık 17 dakika konuşuldu; bu süreye ait ayrıntılı zaman kaydı elimizde yok. Uçuş/otel/kiralama akışlarının canlı olarak başarılı olduğu kanıtlanmış değil.

Şimdi yapılacak ilk iş **A1**. Önce `git status --short` ve `core/callbacks/timing.py` dosyasındaki ilgili fonksiyonu oku; kullanıcı A1'i zaten yaptıysa tekrar yaptırma. `performance.log` varsa önce onu incele. Bütün projeyi yeniden okumak yerine aşağıdaki dosya/fonksiyon haritasını kullan. Bir adımı bitirince bu dosyanın en altındaki ilerleme kaydını güncelle.

Bu konuşmada Codex için seçilen modeli değiştirmek ile Jarvis'in `config/settings.py` / `.env` üzerinden seçtiği modeli değiştirmek ayrı işlerdir. Kullanıcı şu anda Codex modelini değiştirmek istiyor. Jarvis modelini ilk ölçümlerde sabit tut. Daha küçük model seçmek için burada yeni bir model adı veya tasarruf oranı varsayılmadı. Codex'te model seçimi için resmi kaynak: [OpenAI model seçimi](https://learn.chatgpt.com/docs/models).

**Doğrulanmış başlangıç durumu**

- İnceleme başında Git çalışma ağacı temizdi; bu plan dosyası sonradan eklendi.
- `core/callbacks/timing.py` hâlâ yalnızca çağrı sürelerini ve araştırma aracı girdilerini/çıktılarını yazdırıyor. Önceki mesajda önerilen mesaj/karakter sayacı henüz eklenmemişti.
- `performance.log` bulunmadı. Önceki çalışmanın LLM çağrı sayısı, toplam token sayısı veya baskın bekleme nedeni bilinmiyor.
- Proje Python'u `.venv/Scripts/python.exe`. Bu oturumda yalın `python` sistem Python'una gitti ve LangChain bulunamadı. Bu uygulama hatası değildir; ölçüm ve testte sanal ortamın Python'unu açıkça kullan.
- `.venv/Scripts/python.exe -B -m unittest discover -s tests`: **38 test geçti**. Bunlar kontrollü veriler ve mock nesneler kullanıyor; canlı siteleri test etmiyor.
- Yüklü sürümler: LangChain `1.3.18`, langchain-mcp-adapters `0.3.2`.
- Yerel npm önbelleğinde `@playwright/mcp` sürümü `0.0.80`; bağımlılığı Playwright `1.63.0-alpha-2026-08-31`. Başlatma komutu hâlâ `@playwright/mcp@latest`; sonraki çalışmada aynı sürümün geleceğini varsayma.
- `.playwright-mcp` klasöründe eski oturumlardan 648 dosya, toplam yaklaşık 17,9 MB bulundu. En büyük dosya 265.669 bayt. Bunlar tek araştırmanın maliyetini veya her dosyanın modele gönderildiğini göstermez.
- API anahtarı okunmadı/yazdırılmadı. Planlama sırasında canlı araştırma veya model isteği çalıştırılmadı.

**Performans açısından kodun haritası**

| Yer | Gözlenen davranış | Performans açısından anlamı |
| --- | --- | --- |
| `core/agent.py`, `JarvisAgent.__init__` | Tek `thread_id`, `InMemorySaver`, geçmişi küçülten middleware yok | Eski mesaj ve tarayıcı içerikleri birikebilir; her çağrıdaki gerçek yük A1/A2 ile ölçülmeli |
| `core/agent.py`, `run` | İlk `agent.ainvoke` ardından en çok 20 devam çağrısı; iki ilerlemesiz devam turunda çıkış | 20 bir dış döngü sınırıdır, LLM çağrı sınırı değildir. Her `ainvoke` içinde birçok model/araç turu olabilir |
| `core/agent.py`, `run`, `_refresh_final_page_status` | Hazırlık/bitiş kontrolleri esas olarak `ainvoke` döndükten sonra | Araç araştırmayı tamamladıktan sonra grafiğin içinde fazladan model çağrısı yapılabilir |
| `core/tools/browser.py`, `_track_browser_action` | Tüm tarayıcı araçlarını aynı kilitle çalıştırır, her birinde gözlemi geçersiz yapar | Kilit ortak sayfayı korur. Salt kayıt okuyan araçlar da gereksiz yeni snapshot gerektirebilir |
| `core/tools/browser.py`, `_capture_snapshot` | Her çağrıda MCP'den tam snapshot ister, sadece satır içi YAML'ı gözlem olarak saklar | Sayfa zaten okunmuş olsa da tekrar okuma olabilir; hedef alt ağacı parametresi dışarı açılmamış |
| `core/research/evidence.py`, `ObservationStore` | Kanıtları Python belleğinde tutar; mevcut gözlem ve 300 saniyelik yaş kontrolü var | Tam kanıtı tutup modele giden eski metni azaltmak mümkün; tazelik kontrolü korunmalı |
| `core/research/research_manager.py`, `create_comparison_state` | Kategori/ürün kimliği/ürün türü için gerektiğinde ayrı semantik çağrılar | Yeni ürün isteğinde toplam 1–3 başlangıç çağrısı olabilir; bu çağrılara mevcut callback config'i iletilmiyor |
| `core/research/research_tools.py`, `research_add_result` | Yeni kayıt ekler; tam aynı kaydın tekrar eklenmesini engelleyen kontrol yok | Aynı teklif tekrarlanırsa yeni doğrulama ve rapor yükü doğabilir; gerçek tekrarlar logdan aranmalı |
| `core/research/ranking.py`, `get_pending_verifications` | Kayıtlı bütün `PENDING` teklifleri döndürür | Yalnızca en ucuz adayı değil, tüm kaydedilen adayları çözmek gerekir |
| `core/research/comparison_state.py`, `is_ready_to_return` | Bekleyen teklif veya eksik kaynak varsa bitmez | Hız adına kontrolü gevşetmek eksik sonucu tamamlanmış gibi gösterebilir |
| `core/agent.py`, `_build_final_research_context` | Kaynak özetleri, tüm teklifler, fiyat geçmişi ve tam doğrulama ayrıntılarını tekrar verir | Rapor girdisinde tekrarlanan bilgi var; asıl darboğaz olduğu ölçülürse daraltılabilir |
| `core/agent.py`, `_generate_research_report` | Araç bağlanmamış modelle ayrıca bir rapor üretir | Rapor tarayıcıyı tekrar başlatamaz; bu ayrım korunmalı |
| `core/llm/openai.py` | Ana model ve fallback aynı nesne | Hata durumunda aynı sağlayıcıya ek deneme olabilir; iç retry'larla toplam bekleme ölçülmeli |

Önceki düzeltmede devam sınırı 4'ten 20'ye çıkarıldı. Bu, araştırmanın tamamlanmasına yardım ederken daha uzun çalışmaya izin verdi. Her isteğin 20 tur kullandığı veya yavaşlığın tek nedeninin bu olduğu iddia edilmemeli.

**MCP konusunda planlamada bulunan önemli ayrıntı**

Yereldeki `0.0.80` sürümünde olağan tarayıcı eylemlerinin otomatik snapshot'ı çoğunlukla `.yml` dosyasına yazılıyor; araç yanıtının `### Snapshot` bölümünde `[Snapshot](...)` bağlantısı dönüyor. Açık `browser_snapshot` çağrısı ise varsayılan olarak satır içi YAML döndürüyor. Dolayısıyla “her navigate tam sayfayı modele gönderiyor” varsayımı bu sürüm için doğru değil. Tekrar hem sayfanın yeniden okunması hem de açık snapshot'ların geçmişte birikmesi şeklinde olabilir.

Yerel olarak kontrol edilen kaynak:
`C:/Users/recep/AppData/Local/npm-cache/_npx/9833c18b2d85bc59/node_modules/playwright-core/lib/coreBundle.js`

- `browser_snapshot` şeması: yaklaşık satır 64301; `target`, `filename`, `depth`, `boxes` destekliyor.
- `Response4._build`: yaklaşık satır 65658; `snapshotToFile` seçimi ve dosya bağlantısı üretimi.
- Varsayılan çıktı klasörü: yaklaşık satır 65039; çalışma dizini altında `.playwright-mcp` veya bazı durumlarda geçici dizin.
- `browser_console_messages` ve `browser_network_requests` bu sürümde `readOnly` olarak tanımlı.

Bu dosya büyük bir bundle; tamamını okuma. `rg -n --max-columns 240` ve küçük satır aralıkları kullan. Önbellek yolu/sürüm değişmişse yeniden bul. Bir dosyanın varlığını güncel fiyat kanıtı sayma; yalnızca o anki başarılı araç yanıtının ürettiği dosya değerlendirilebilir.

**Değişiklik boyunca korunacak davranışlar**

1. Keşifte 4.500 TL görülen teklif satıcıda 6.000 TL ise güncel tutar 6.000 TL olur; 4.500 TL geçmişte kalır. Diğer satıcıdaki doğrulanmış 5.200 TL bundan ucuzdur.
2. Satıcı, teklif/ürün kimliği, URL, fiyat düğümü, para birimi ve kapsam kanıtları birbirinden koparılamaz.
3. Uçuşta kişi başı, otelde gecelik, kiralamada günlük ücret tam talep toplamı değildir. Bilinmeyen zorunlu ücret sıfıra çevrilemez.
4. Farklı para birimleri doğrudan sayısal olarak karşılaştırılamaz; üyelik/kupon fiyatı kendiliğinden herkese açık fiyat sayılamaz.
5. Planlanan kaynaklar ve kaydedilen sonuçlar raporda korunur. Doğrulanamayan daha ucuz gözlem gizlenmez.
6. Kazananın son sayfa kontrolü taze gözlemle yapılır; son fiyat değişirse sıralama tekrar açılır.
7. Aynı tarayıcı sayfasında birbirine bağlı navigasyonlar paralel başlatılmaz. Mevcut `_action_lock` kaldırılmaz.
8. Tarayıcı/sayfa metni talimat yetkisi kazanmaz. Güvenlik middleware'i kısa yoldan atlanmaz.

Mevcut doğrulamanın sınırı: Seyahat tarihleri, yolcu/oda sayıları gibi koşulların çoğu hâlâ prompt ve alıntılanan `scope_evidence` üzerinden yürütülüyor; `criteria` yapılandırılmış biçimde doldurulmuyor. Performans çalışması bunların tümünü mekanik olarak doğrulanmış hale getirmiş sayılmaz. Bu ayrı doğruluk çalışmasıdır; hız kazanmak için mevcut kontrolleri de zayıflatma.

**Uygulama sırası ve karar kapıları**

| Adım | Küçük teslim | Geçiş koşulu |
| --- | --- | --- |
| A1 | Mesaj/karakter sayacı ve bir başlangıç kaydı | Aynı araştırmanın süre/araç çıktıları okunabiliyor |
| A2 | Gerekirse istek/evre/token özeti | Sürenin ve çağrıların ağırlığı görülebiliyor |
| B | Araştırma hazır olduğunda model döngüsünden çıkış | Hazır durumdan sonra araştırma modeli çağrılmıyor, tek rapor çağrısı kalıyor |
| C1 | Eski snapshot metinlerini model girdisinde daraltma | Ham kanıtlar korunuyor, model girdisi küçülüyor, sonuç doğruluğu korunuyor |
| C2 | Gerekiyorsa kısa araştırma durumunu her model turuna verme | Eski sayfa metni kaldırılınca model kaydedilmiş sonuçları kaybetmiyor |
| D1 | Salt tanılama okumalarının gözlemi gereksiz bozmasını önleme | Yeniden snapshot talebi azalıyor, gerçek sayfa değişikliği gözlemi bozuyor |
| D2 | Başarılı eylemin zaten ürettiği snapshot'ı kullanma | Aynı sayfanın gereksiz ikinci okunması azalıyor; son kontrol taze kalıyor |
| E | Logun gösterdiği küçük ek işler | Aynı sonucu daha az model/araç işiyle üretme |
| F | Dört kategori için doğruluk ve performans karşılaştırması | Kazanç ölçülmüş, kapsam/kanıt gerilemesi yok |

A1'den sonra darboğaza göre sıra uyarlanabilir. Örneğin süre çoğunlukla navigasyon timeout'larında geçiyorsa C'nin duvar saati kazancı düşük kalabilir; D ve ilgili beklemeler öne alınır. Her maddede başarı ölçülüyorsa sırf listedeki tüm işleri yapmak için yeni refaktöre devam etme. Yüzde veya dakika cinsinden hızlanma sözü verme.

**A1 — Kullanıcıya gösterilecek ilk değişiklik**

Dosya: `core/callbacks/timing.py`.
Yalnızca `TimingCallback.on_chat_model_start` fonksiyonunu aşağıdakiyle değiştirmesini anlat:

```python
    def on_chat_model_start(
        self,
        serialized,
        messages,
        *,
        run_id,
        **kwargs,
    ):
        self.llm_start_times[run_id] = time.perf_counter()

        message_count = sum(len(batch) for batch in messages)
        content_chars = sum(
            len(str(message.content))
            for batch in messages
            for message in batch
        )

        print(
            f"[Timing] LLM input: "
            f"messages={message_count}, "
            f"content_chars={content_chars}"
        )
```

Anlatılacak neden: Süre ölçümü zaten var; modele tekrar tekrar ne kadar konuşma içeriği gönderildiğini de görmemiz gerekiyor. Karakter uzunluğu token sayısı değildir. Bu sayaç araç şemalarının boyutunu, bazı ayrı tool-call alanlarını veya görsel tokenlarını ölçmez; bunlar için A2'de sağlayıcının kullanım bilgisi gerekir.

PowerShell'de proje kökünden başlangıç kaydı:

```powershell
.\.venv\Scripts\python.exe -u main.py 2>&1 | Tee-Object -FilePath performance.log
```

Aynı Logitech araştırma komutu, aynı koşullar ve yeni süreçle başlat. `Jarvis is ready` geldikten sonra komutu gir; işlem bitince `exit` yaz. Pipe nedeniyle `You:` istemi gecikmeli görünebilir; program hata vermediyse hazır mesajından sonra girdiyi yazmak mümkündür. Kullanıcının elinde zaten uygun bir kayıt varsa sırf yeniden ölçmek için uzun araştırmayı tekrarlatma.

Kaydı incelerken: LLM tamamlanma sayısı/toplamı/en uzun çağrılar; araç adına göre sayı ve süre; `browser_snapshot` tekrarları; doğrulama retleri ve sebepleri; aynı URL/teklif tekrarları; `FINAL PAGE CONFIRMED` sonrasındaki çağrılar; giriş karakterlerinin ilk/orta/son değerleri. Araç sürelerinin toplamı paralel işler ve kapsayan işlemler yüzünden duvar saatine eşit olmayabilir. Kaydın içinde tam araştırma girdileri olabileceği için logu Git'e eklemek bu işin parçası değildir.

**A2 — Ölçüm hâlâ eksikse, üç küçük parça**

A2a, yalnızca `core/callbacks/timing.py`:

- İstek başına sıfırlanan sayaçlar: başarılı/hatalı LLM çağrıları, süreleri, araç adı başına sayı/süre/hata, en büyük mesaj içerik boyutu.
- Anahtar olarak mevcut `run_id` kullan; eşzamanlı çağrıları tek `start_time` değişkenine koyma. Chat/LLM başlangıç callback'lerinin aynı run için iki kere sayılmasını önle.
- `on_llm_end` içinde `response.generations` içindeki mesajın `usage_metadata` alanından `input_tokens`, `output_tokens` ve varsa `input_token_details.cache_read` oku. Aynı veriyi ayrıca `llm_output` üzerinden tekrar toplama. Sağlayıcı veri vermiyorsa `unknown` say; sıfır maliyet varsayma.
- Callback hataları araştırmayı durdurmamalı. Hatalı çağrılar da elapsed time ile ölçülmeli.
- Önce bağımlılık eklemeden mevcut callback'i genişlet. JSONL yalnızca kayıt çözümlemeyi kolaylaştırmak için gerekirse eklenir; tam prompt/snapshot yeni telemetri alanlarına kopyalanmaz.

A2b, `core/agent.py` ve `main.py`:

- `run` girişinde ölçümü başlat, `try/finally` ile hatada da özet çıkar. Yeni istek önceki isteğin sayaçlarını taşımamalı.
- Gerçek görev planlama süresi, araştırma süresi, rapor süresi ve dış devam turu sayısı ayrı görünsün.
- `main.py`'de ölçüm şu anda tarayıcı açıldıktan sonra başlıyor. Başlangıçta bekleme şikâyeti de varsa `BrowserManager.start()` süresini ayrıca göster; kullanıcı komutunun süresine katma.
- Toplam LLM/araç sürelerini bağımsız sayaç olarak sun. Eşzamanlı aralıkları toplarken “toplam süre = hepsinin toplamı” sonucunu çıkarma.

A2c, `core/research/research_manager.py` ve `core/agent.py`:

- `create_comparison_state` ve üç semantik yardımcıya geriye uyumlu `config: dict | None = None` parametresi ekle; gerçek `.ainvoke` çağrılarına ilet.
- `run` içinde `_get_config()` oluşturmayı planlamadan önceye taşı. Evre etiketini kopyalanmış config metadata/tags üzerinden taşı; paylaşılan dict'i eşzamanlı kullanımda değiştirme.
- Böylece baştaki 1–3 çağrı da görünür olur. Ölçüm amacıyla model çağrılarının içeriğini veya sırasını değiştirme.

Kontrol: Mock bir başarılı çağrı, bir hata ve token bilgisi olmayan yanıt; iki istek arasında sıfırlama; planlama/rapor çağrılarının sayılması. Geniş bir test altyapısı kurma.

**B — İş bitince araştırma modelini tekrar çağırma**

Dosyalar: `core/context.py`, `core/agent.py`; anlamlı kontrol için mevcut test dosyası veya yeni küçük middleware testi.

Sorun: `is_ready_to_return()` dış döngüde kontrol ediliyor. `research_confirm_final_page` işi tamamladıktan sonra create_agent kendi içinde tekrar modele gidebilir; model yeni bir tarayıcı işlemi seçerse son sayfa doğruluğu bile yeniden bozulabilir.

Uygulama tasarımı:

1. `RequestContext` dataclass'ına varsayılanı `False` olan `research_active: bool` ekle. `run` bunu o isteğin çözümlenmiş `task_type == TaskType.COMPARISON` değerinden doldursun. Sırf eski bir comparison state var diye normal sohbet/eylem isteğini bitirme.
2. `JarvisAgent.__init__` içinde, `self` durumunu okuyabilen küçük bir middleware oluştur. Yüklü LangChain `before_model(can_jump_to=["end"])` destekliyor.
3. Her model çağrısından önce: bu istek araştırma değilse devam et; `_refresh_final_page_status()` çalıştır; aktif state gerçekten `is_ready_to_return()` ise `{"jump_to": "end"}` döndür; değilse `None`.
4. Middleware'i create_agent listesine ekle. Rapor için mevcut `_generate_research_report` çağrısı korunur. Bu çağrı grafiğin dışında ve araçsız olduğundan completion guard tarafından engellenmez.
5. Bir model yanıtında zaten verilmiş araç çağrılarını ortasında kesme; kontrol bir sonraki model sınırında yapılır. Bekleyen tool call cevaplarının eşleşmesini bozma.

Yerel API kanıtı: `.venv/Lib/site-packages/langchain/agents/middleware/types.py`, `before_model` yaklaşık satır 952–1010. `jump_to`, aynı dosyada geçici (`EphemeralValue`) durum olarak tanımlı. Yine de ardışık iki kullanıcı isteğini test et.

Kabul kontrolleri:

- Son teklif doğrulanıp state hazır olduktan sonra araştırma modeli tekrar çağrılmaz; rapor modeli bir kez çağrılır.
- Eksik kaynak, `PENDING` teklif, geçersiz/eski son gözlem ve gerekli ama tamamlanmamış staging durumlarında bitirmez.
- Tüm kaynakların sonuçsuz olduğu mevcut geçerli bitiş davranışını korur.
- Bitmiş araştırmanın ardından normal sohbet isteği model çağrısına ulaşır. Yeni araştırma da yanlışlıkla bitmiş sayılmaz.
- Gerçek küçük create_agent grafiği + sahte chat model ile entegrasyon kontrolü yap; yalnızca middleware fonksiyonunun dict dönmesini test etmek yeterli değildir.

Bu adım 20 sınırını düşürmez. Önce tamamlanan işi durdurur; eksik araştırmaya verilen süreyi kesmez.

**C1 — Eski snapshot içeriklerini yeniden göndermeyi azalt**

Dosyalar: yeni `core/browser_context.py` (küçük, bağımsız yardımcı/middleware), `core/agent.py`; gerekirse test için `tests/test_browser_context.py`.

Karar: Önce kalıcı mesajları silmek veya LLM'e geçmiş özetlettirmek yerine, modele gönderilen eski tarayıcı ToolMessage içeriklerini daralt. `ObservationStore` tam kanıtı, LangGraph geçmişi ham mesajları saklamaya devam etsin. Bu ilk sürüm RAM büyümesini çözmez; model girdisini azaltır.

Yerel API: async `@wrap_model_call` veya `AgentMiddleware.awrap_model_call`; `request.override(messages=...)`. Sync hook ile async agent karıştırılmamalı. Uygulama öncesi `.venv/.../middleware/types.py` içindeki mevcut imzayı kontrol etmek yeterli; paket yükseltme gerekmez.

Güvenli ilk kapsam:

- Yalnızca eski, açık `browser_snapshot` yanıtlarını işle. MCP navigate/click yanıtlarının yapısını ilk sürümde kesme; bunlar dosya bağlantısı ve eylem/hata bilgisi içeriyor olabilir.
- En yeni açık snapshot, `current_observation_id` ile eşleşen snapshot ve son iki tamamlanmış assistant/tool grubundaki mesajlar aynen kalsın. Henüz modele gösterilmemiş son araç grubuna dokunma.
- Yalnızca gözlem kimliği ve URL'si güvenilir biçimde ayrıştırılabilen, tam ham karşılığı saklı snapshot eskiyse daralt. Ayrıştırılamayan yanıtı değiştirme.
- Aynı `ToolMessage` türünü, `id`, `tool_call_id`, `name`, `status` ve diğer metadata alanlarını koru; `model_copy(update={"content": ...})` gibi kopyalama kullan. Orijinal nesneyi yerinde değiştirme.
- Özet metni yalnızca araç adı, observation ID, gözlem URL'si ve “bu eski sayfa içeriği model girdisinden çıkarıldı; güncel kanıt değildir” bilgisini taşısın. Eski fiyattan yeni doğrulanmış toplam üretme.
- AIMessage içindeki tool-call kimlikleri, Responses içerik blokları/reasoning alanları, sistem talimatları ve gerçek kullanıcı mesajları aynen korunmalı. `messages[-N:]` gibi kör liste kesmesi yapma.
- Kısa içerikleri işlemeyebilmek için yaklaşık 4.000 karakterlik teknik eşik başlangıç önerisidir; evrensel token limiti değildir. Güncel snapshot eşikten büyük olsa da kesilmez.

Modelin eski keşif verisini yeniden incelemesi gerekebilir. Daraltmayı açmadan önce geri okuma yolunu sağla: saklı bir observation'ı ID ile salt okunur döndüren küçük bir araç eklenebilir (`research_read_observation`). Açıklamasında bunun **arşiv** olduğu, current olmadığı ve yeniden doğrulama yerine geçmediği açık olsun; store.capture veya tazelik zamanını güncellemesin. `offer_ref` verilirse mevcut `get_snapshot_subtree` kullanılabilir. Aracın çıktısı son grupta korunur. Bu araç eklenirse mevcut güvenlik politikasına salt okuma olarak kaydet; tarayıcı eylemi yapmasın. Kullanıcıya bu parça ayrı küçük adımda anlatılmalı.

Kabul kontrolleri:

- Art arda büyük snapshot içeren yapay bir geçmişte modele giden karakter sayısı azalır; ham geçmiş ve ObservationStore değişmez.
- Son snapshot ve güncel sayfada kullanılan ref'ler aynen kalır. Eksik metadata ve hata mesajı korunur.
- Bir assistant mesajındaki birden çok tool call ve cevap sırası geçerli kalır; sahte modelle gerçek grafiği çalıştır.
- Arşivden okunan eski sayfa `require_current` kontrolünü geçemez; navigasyon sonrasında eski ref güncel diye sunulmaz.
- 4.500 → 6.000 fiyat değişimi ve diğer satıcıdaki 5.200 sonucu korunur.
- Sağlayıcının cache_read bilgisi varsa izlenir. Girdi küçülmesi tek başına aynı oranda gecikme/ücret düşüşü anlamına gelmez; geçmişin farklılaştırılması prefix cache kullanımını etkileyebilir.

**C2 — Kısa araştırma durumu, yalnızca ihtiyaç varsa**

Dosyalar: `core/agent.py`, C1 middleware'i veya küçük `core/research/progress.py`.

Tam son rapor bağlamını her model turuna ekleme. Gerekiyorsa Python state'inden deterministik kısa bir görünüm üret: kategori, özgün istek, bekleyen kaynaklar, sıradaki birkaç pending teklifin ID/URL/satıcı bilgisi, doğrulanmış herkese açık toplamların para birimine göre en iyisi, sonlandırma/son gözlem durumu. Ayrıntılara mevcut `research_status` / kayıtlar üzerinden ulaşılabilsin.

Bu görünüm yeni bir LLM çağrısıyla oluşturulmaz. Sayfadan gelen başlık/notları talimat olarak sunma; veri olarak JSON içinde taşı. Kullanıcının tarih/kişi/ürün varyantı koşulları kaybolmamalı. Fiyat sıralamasında `strict=True` kuralları korunur. Görünümde sınırlandırılmış liste tüm teklifleri state'den silmek anlamına gelmez.

Bu adım yalnızca C1 sonrasında modelin kayıtlı işleri unutması veya gereksiz `research_status` turları ölçülürse uygulanır. Güncel prompt'a büyük yeni talimat paketleri ekleme.

**D1 — Salt tanılama okumasında gözlemi koru**

Dosya: `core/tools/browser.py`, `_track_browser_action`.

Şu an her MCP aracı `invalidate_current()` çağırıyor. İlk kapsam yalnızca yüklü sürümde gerçekten salt kayıt okuduğu kontrol edilen `browser_console_messages` ve `browser_network_requests` olsun. Bunlar için mevcut gözlemi koru; kilit yine alınsın. İsimleri belirsiz veya yeni gelen araçlar varsayılan olarak gözlemi bozsun.

`browser_evaluate`, kod çalıştıran araçlar, navigate/click/fill/select/back/reload, sekme açma/seçme/kapama, dialog işlemleri, viewport değişimi ve bekleme işlemleri güvenli okuma listesine eklenmez. Salt okuma etiketini körü körüne her araca genelleme. Yaş kontrolü 300 saniye olarak çalışmaya devam eder; bu süre güncellenmez.

Kontrol: Console/network okuması observation ID'yi değiştirmez; navigate ve bilinmeyen araç değiştirir; eski observation süre nedeniyle yine reddedilir. Bu iki aracın logda kullanımı yoksa kazanım bekleme ve adımı ötele.

**D2 — Eylemin ürettiği snapshot'ı tekrar kullan**

Dosyalar: `core/tools/browser.py`; küçük ayrıştırıcı dosyası gerekirse `core/browser_snapshot.py`; `core/prompts.py` içinde yalnızca değişen gözlem kaynağını açıklayan birkaç cümle; ilgili testler.

Önce mevcut MCP sürümünü sabitleyerek karşılaştırılabilir ölçüm yapma seçeneğini kullanıcıya açıkla. Yerelde doğrulanan `0.0.80` sadece adaydır; yeni bir sürümü araştırmadan önerme. Pinleme başlangıç değişkenliğini azaltır; tek başına 17 dakikayı çözmez.

D2a: `_capture_snapshot` içindeki URL/YAML ayrıştırmasını küçük saf yardımcıya çıkar. Önce davranış değişmeden mevcut testleri çalıştır. Desteklenen başarılı satır içi çıktı, hata, boş çıktı ve yanlış biçim fixture'ları olsun.

D2b: `_track_browser_action` içindeki `await handler(request)` sonucunu **kilit bırakılmadan** değerlendir. Adapter `0.3.2` burada çoğunlukla MCP `CallToolResult` verir; `ToolMessage`/`Command` gibi diğer türler de mümkündür. Beklenmeyen türü zorla dönüştürme; mevcut davranışla döndür.

- Başarılı, güncel eylem çıktısında güvenilir Page URL ve tam snapshot varsa bu verilerle `ObservationStore.capture` yap; Observation ID'yi araç yanıtına ekle.
- Yerel `0.0.80` dosya bağlantısı döndürüyor. Yalnızca bu gerçek araç sonucunun üst düzey `### Snapshot` bölümündeki tek bağlantıyı kabul et. `### Result`, sayfa metni veya model argümanından bir dosya yolu seçme.
- MCP çalışma/çıktı kökü açık ve bilinir olmalı. Yol çözümlemesinden sonra dosyanın izin verilen `.playwright-mcp`/belirlenmiş çıktı kökü içinde kaldığını doğrula; uzantı, dosya varlığı ve içerik kontrollerini yap. Rasgele en yeni `.yml` dosyasını bulup kullanma, dış dizin/URL okuma yapma.
- Dosyayı mevcut araç işleminin içinde oku. Yeni gözlem zamanı bu başarılı işlemle ilişkili olsun; eski dosyayı sonradan okuyup “şimdi yakalandı” diye damgalama. Arşiv geri okuması ile bu mekanizma ayrıdır.
- Eylem sonrasındaki HTTP hata/çökme, boş veya eksik snapshot, yalnızca delta veya çözülemeyen dosya için yeni doğrulama gözlemi oluşturma. Normal `browser_snapshot` yoluna dön.
- Arayüz çıktısında snapshot metnini yalnızca bir kez sun. Yeni observation ID fiyatın doğrulandığını göstermez; `validate_quote` ve `apply_quote` aynen gerekli kalır.
- İlk teklif doğrulamasında güncel eylemden gelen uygun observation varsa fazladan `browser_snapshot` zorunlu olmasın. Prompt bu seçeneği açıkça anlatsın.
- **Son kazanan kontrolünde açık yeni `browser_snapshot` zorunluluğu ilk uygulamada korunur.** Eski capture'ı veya aynı verification observation ID'sini final için kullanma.

Kabul kontrolleri: Satır içi ve dosyalı gerçek biçimler; Windows göreli yol/boşluk; dış köke kaçan yol; yanıttaki sahte ikinci Snapshot başlığı; hatalı/boş/delta içerik; iki ardışık navigasyonda ilk ID'nin geçersiz kalması; yönlendirme/sekme değişiminde dönen gerçek sayfa URL'si; güncel fiyat kontrolü; ayrı final snapshot. Mock MCP ile tekrarlanabilir test, ardından bir gerçek site denemesi gerekir.

D2 dosya desteği fazla büyük hale gelirse güvenli alternatifi seç: yalnızca satır içi biçimi destekle, dosya biçiminde mevcut explicit snapshot fallback'i koru. Bu sürümde kazanımı sınırlı olacağını açıkça yaz. Dosya desteği yeni genel dosya okuma yetkisine dönüştürülmez.

**E — Sonraki işler yalnızca ölçüme göre**

Her madde bağımsızdır; hepsi otomatik uygulanacak bir paket değildir.

E1, gerçekten aynı kaydın tekrar eklenmesi:

- `research_add_result` / `ComparisonState.add_result` çevresinde aynı kaynak içinde tam aynı teklif ve aynı verinin tekrarını idempotent yapmayı değerlendir.
- Yalnızca kesin eşitlik: kaynak, tam teklif URL'si, satıcı, SKU/varyant, para birimi, koşullar ve talep kapsamı. Uçuş/otel/kiralama kapsamı güvenilir biçimde belirlenemiyorsa birleştirme.
- Tek başına aynı ürün adı, aynı domain veya aynı satıcı yeterli değildir. Farklı kaynak kayıtlarını kaybetme. Keşif ve fiyat geçmişini koru; değişen fiyat/URL/koşulu tekrar diye yutma.
- Basit tam tekrar mevcut result ID'yi döndürür; doğrulamayı ve finalizasyonu sebepsiz bozmaz. Farklı veri yeni veya güncelleme akışına açıkça yönlendirilir.
- Kontrol: aynı ürün/farklı satıcı; aynı otel/farklı tarih; aynı uçuş/farklı bagaj; aynı araç/farklı iade yeri; tam aynı kayıt. Mevcut `urls_match` tüm seyahat parametrelerini kapsamadığından genel dedupe anahtarı olarak kullanılmaz.

E2, başlangıçtaki sınıflandırma çağrıları:

- Yalnızca A2 planlama süresinin anlamlı olduğunu gösterirse `research_manager.py` içinde mevcut keyword hızlı yolu koruyarak gereken semantik alanları tek yapılandırılmış cevapta birleştir.
- Kategori, ürün türü ve ürün kimliği birbiriyle tutarlı olmalı. Yeni bilgi uydurmama, şema doğrulama ve mevcut kaynak planını koruma testleri gerekir.
- Sonuçtan bağımsız işleri paralelleştirmek mümkün olsa da sadece birkaç başlangıç çağrısının uzun tarayıcı akışını tek başına düzeltmesi beklenmez.
- Her şeyi tekrar keyword listelerine çevirmek genel uçuş/otel/kiralama hedefini karşılamaz. Modelle ilgili optimizasyon ilk adım değildir.

E3, salt durum kaydı için çok sayıda LLM turu:

- Önce gereksiz `research_set_offer_url` çağrılarını kaldıracak yönlendirmeyi kullan: `research_add_result` zaten `offer_url` kabul ediyor. Tam URL biliniyorsa kayıtta verilebilir. Değişen redirect URL'sini yine güncellemek gerekir.
- Bağımlı araçlar tek model yanıtında paralel çağrılmamalı; daha ID dönmeden verify başlatma.
- Ancak log bunu ana maliyet gösterirse add/set/verify mantığını ortak Python yardımcıları üzerinden birleştiren dar bir araç tasarla. Decorated tool `.invoke` çağrılarını iç içe sokup sahte ölçüm/güvenlik dolanması yaratma.
- Bütün doğrulamalar aynı `OfferQuote`, `validate_quote`, `apply_quote` yolundan geçsin. Başarısız kaydın state'de ne bırakacağı açık olsun; başarı numarası uydurma. Bu adım küçük açıklanabilir parçalara bölünmeden uygulanmaz.

E4, tekrar deneyen veya bekleyen tarayıcı:

- Araç adına ve aynı URL+aksiyon+argüman+beklenen sonuç imzasına göre gerçek tekrarları bul. Aynı hata tekrarında bağlama uygun alternatif veya açıklamalı kısmi sonuç düşün; fiyat doğrulamasını atlama.
- Sabit sleep / genel network-idle yerine görünür sonuç, yüklenme işaretinin bitmesi veya URL gibi gerekli durumu beklemek siteye göre değerlendirilebilir. Süreleri ölçmeden bütün timeout'ları düşürme.
- 20 dış devam sınırını gerçek model çağrı sınırı sanma. İlerleme imzası yalnızca kalıcı araştırma state'ini görüyor; tarayıcıda form doldurmak ilerleme olduğu halde sayılmayabilir. İmza/bütçe değişikliği ayrı kontrol ister.
- Mutlak süre veya çağrı bütçesi daha hızlı tamamlanmış araştırma demek değildir. Bütçe biterse kaynakları `completed`/`blocked` diye uydurmak yerine eksik araştırma olarak raporla.

E5, rapor pahalıysa:

- `_build_final_research_context` içindeki aynı verinin kaynak özeti + tam doğrulama alıntısı + tüm sonuçlar şeklinde tekrarını azalt. Tam kanıt Python'da kalır; raporda kaynak, satıcı, güncel fiyat/toplam, para birimi, koşul, kapsam, ücret belirsizliği, link, doğrulama durumu ve fiyat değişimi korunur.
- Tek araçsız rapor çağrısını koru. Daha sonra gerekirse Python ile tam teklif tablosu + kısa model açıklaması değerlendirilebilir; çıktı dilini ve tüm kaynakların görünmesini koru.
- Test şu an rapor modeline verilerin iletilmesini kontrol ediyor; modelin nihai metinde hepsini yazacağını garanti etmiyor. Testin kanıtını abartma.

E6, büyük güncel snapshot:

- C1 sadece eski içerikleri azaltır. Son sayfa tek başına çok büyükse Python'da tam snapshot'ı saklayıp modele seçili alt ağacı sunma ayrıca değerlendirilebilir.
- Seçim satıcı/fiyat/kapsam/ücret kanıtlarını birlikte kapsamalı; yalnızca ilk N karakter veya fiyat regex'iyle kesilmez. Eksik alanda tam içerik geri okunabilir olmalı.
- `browser_snapshot(target, depth)` MCP tarafından desteklense de Jarvis wrapper'ı şu anda parametresizdir. Hedeflenmiş snapshot'ın kısmi olduğunu açıkça kaydet; tam sayfaymış gibi karşılaştırma yapma. Önce C1 ve D2'nin kazancını ölç.

**Bu performans turunda ilk çözüm olarak seçilmeyenler**

- Kaynak sayısını azaltmak, yalnızca ilk ucuz sonucu doğrulamak veya pahalı keşif fiyatını kesin alt sınır sayıp diğer adayları atlamak. Keşif fiyatı hem yukarı hem aşağı değişebilir.
- `PENDING` kontrolünü kaldırmak veya denemeden `BLOCKED` işaretlemek.
- Eski observation'ı yeni kimlikle/tarihle güncel gibi sunmak; 300 saniyelik kontrolü rahatlatmak; final sayfa kontrolünü kaldırmak.
- Ortak tarayıcı kilidini kaldırıp siteleri `asyncio.gather` ile aynı sayfada açmak. Gelecekte paralellik gerekirse her işin ayrı browser/context/ObservationStore sahibi olması ve sonuçların kanıtlı birleşmesi gerekir; bu ayrı mimari adımdır.
- Bütün kategori ve site akışlarını yeniden yazmak. Uyarlayıcılar form/filtre/navigasyon işini hızlandırabilir ama aynı doğrulama çekirdeğini kullanmalı; fiyatı siteye özel sabit regex ile “kesin” ilan etmemeli.
- Sırf hızlı görünsün diye araştırmayı erken kesmek veya Jarvis modelini ölçüm ortasında değiştirmek.
- Tüm konuşmayı silmek, yeni thread açarak kullanıcının düzeltmelerini kaybetmek veya yeni ücretli özetleme modeli eklemek.

**F — Doğrulama ve ölçüm protokolü**

Her değişiklikte yeni çalışma ağacını kontrol et; kullanıcı değişikliklerini koru. Sadece ilgili küçük parçanın testi ve gerekli mevcut regresyon kontrolleri çalıştırılır. Tam suite komutu:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
git diff --check
```

Kontrollü regresyon senaryoları:

| Senaryo | Beklenen sonuç |
| --- | --- |
| Keşif 4.500, satıcı 6.000, başka doğrulanmış teklif 5.200 | 5.200 karşılaştırmada önde; 4.500 geçmişte |
| Aynı ürün, farklı satıcının linkindeki fiyat | Mevcut satıcının fiyatı diye doğrulanmaz |
| Birim/gece/gün/kişi başı fiyat | Tam talep toplamı olarak sıralanmaz |
| Bilinmeyen zorunlu ücret | Sıfır veya kesin toplam uydurulmaz |
| Para birimi farklı veya kupon koşulu var | Ayrı gösterim, yanlış ortak kazanan yok |
| Bütün kaynaklar sonuçsuz/erişim engelli | Açıklamalı bitiş; sahte kazanan yok |
| Son kontrol sırasında fiyat değişiyor | Finalizasyon tekrar açılır |
| Final sonrası sayfa değişiyor | Eski son sayfa doğrulaması geçersiz |
| Geçmiş daraltıldıktan sonra eski gözlem okunuyor | Arşiv olduğu belli, güncel kanıt sayılmıyor |

Canlı ölçüm: Önce aynı ürün isteğiyle önce/sonra karşılaştırması. Site fiyatı değişebileceği için aynı sayısal fiyat zorunlu değil; o anki satıcı sayfası ve toplamla tutarlılık zorunlu. Sonra kullanıcıyla tarih/yer/kişi koşulları belli birer uçuş, otel ve araç kiralama isteği seç. Geçmiş tarih uydurma. Canlı denemelerde kaynak planı, erişim durumu, bulunan/doğrulanan teklif sayısı ve eksik iş sayısı kaydedilsin. Dört kategori için sadece yapay scope metni kullanan testler gerçek rezervasyon akışı başarısı sayılmaz.

Karşılaştırma tablosuna yazılacak alanlar: commit/değişiklik, tam istek, Jarvis sağlayıcı/model ve MCP sürümü, toplam duvar saati, model sayısı ve input/output/cache tokenları varsa, planlama/araştırma/rapor süreleri, araç sayıları, snapshot sayısı, en büyük girdi, dış devam turu sayısı, kaynak kapsamı, doğrulanmış teklif sayısı, hatalı fiyat/kapsam sayısı.

Başarı: Aynı kapsam ve doğrulukla gereksiz çağrı/tekrar/metin yükü azalmalı ve canlı ölçümde bunun etkisi görülmeli. Site erişimi veya bulunan teklif sayısı değişmişse süreleri birebir karşılaştırılabilir diye sunma. Aynı süreçte ikinci istekte geçmiş büyümesi ayrıca kontrol edilir. İlk sonucun varyansı yüksekse sınırlı tekrar yap; her küçük değişiklikten sonra dört uzun canlı tur çalıştırma.

**İlerleme kaydı**

- Planlama tamamlandı; uygulama adımları başlamadı.
- Başlangıç regresyonu: 38 test geçti, 10 Eylül 2026.
- A1: bekliyor. `on_chat_model_start` sayaç değişikliği ve `performance.log` henüz yok.
- Sonraki yanıtta: kullanıcıya yalnızca A1'i anlat veya mevcut log geldiyse analiz et. Kullanıcı modeli değiştirmiş olsa da çalışma biçimi aynı kalır.

**13 Eylül 2026 — kullanıcının yetkilendirdiği ilk ürün hedefi**

- A1/A2/B/C1/C2'nin zaten uygulandığı kod ve eski performans kayıtları üzerinden doğrulandı; tekrar uygulanmadı.
- Referans seçimine dayalı ürün doğrulaması, kanıtlı keşif/engel kaydı, adet/kargo kontrolleri, teklif bölümleri arasındaki ilişki kontrolü ve deterministik bağlantılı rapor eklendi. MCP `0.0.80` sürümüne sabitlendi; Jarvis modeli değiştirilmedi.
- Başlangıçtaki 59 test, 18 yeni regresyonla **77 test** oldu; tamamı geçti. Canlı testte gerçek satıcı/tek adet/fiyat/kargo doğrulandı; tam yedi kaynaklı kabulün sonucu uygulama kaydında ayrıca tutuluyor.
- `scripts/research_acceptance.py` gerçek koşunun kaynaklarını, doğrulanmış kayıt sayısını, son sayfa kontrolünü, süre/token ölçülerini, kod dosyası özetlerini ve tarayıcı gözlemlerini `artifacts/` altında saklıyor. Başarısız/kısmi koşular başarı sayılmıyor.
- Bu teslim seyahat kapsamı, görev iptali/değiştirme, tüm güvenlik kararları veya dört kategorili F kabulünün tamamlandığı anlamına gelmez. Hız yüzdesi için aynı kapsamda başarılı önce/sonra koşusu hâlâ gereklidir.
