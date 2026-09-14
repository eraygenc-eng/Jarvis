Jarvis proje incelemesi — 13 Eylül 2026

İncelenen commit: `b3e45ed`. İnceleme kapsamı: `main.py`, `config`, `core` altındaki 33 Python dosyası, mevcut testler, bağımlılıklar, `docs/performance-plan.md` ve dört performans kaydı. Uygulama kodu değiştirilmedi. Canlı model çağrısı, site araştırması veya gerçek masaüstü/tarayıcı eylemi çalıştırılmadı; aşağıdaki ek kontroller bellek içi veriler ve sahte model/araç nesneleriyle yapıldı. `.env` içeriği okunmadı veya rapora alınmadı.

**Genel değerlendirme**

Jarvis'in araştırma altyapısında faydalı kontroller var: kaynak durumları, bekleyen teklifler, gözlem tazeliği, fiyat geçmişi, para birimine göre sıralama, ayrı nihai rapor çağrısı ve araştırma tamamlandığında model döngüsünü durdurma. Ancak mevcut loglar, başarılı ve doğru bir araştırmanın hızlandığını göstermiyor. Üç tamamlanmış ölçümün hiçbirinde doğrulanmış teklif yok. Bazı doğrulama kuralları doğru veriyi biçim uyuşmazlığı nedeniyle reddederken, başka kurallar yanlış kapsam veya başka teklife ait fiyatı kabul edebiliyor.

Bu nedenle sıradaki iş yalnızca performans planının D adımına geçmek olmamalı. Önce kanıt ile teklif arasındaki ilişki ve başarısız araştırmanın yönetimi düzeltilmeli; ardından aynı kapsamda başarılı bir araştırma ölçülmeli.

**Ölçülen mevcut durum**

| Kayıt | Toplam süre | LLM çağrısı | LLM süre toplamı | En büyük mesaj içeriği | Kaydedilen teklif | Başarılı teklif doğrulaması |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `performance.log` | Tamamlanmış toplam yok; UnicodeEncodeError ile sonlanmış | 44 kayıtlı | 493,12 sn kayıtlı | 503.205 karakter | 6 | 0 |
| `performance_before_b.log` | 275,50 sn | 37 | 265,10 sn | 358.927 karakter | 3 | 0 |
| `performance_after_c1.log` | 563,15 sn | 145 | 507,11 sn | 137.693 karakter | 12 | 0 |
| `performance_after_c2.log` | 200,27 sn | 51 | 176,70 sn | 144.281 karakter | 2 | 0 |

Tamamlanmış kayıtlarda süre ve token değerleri kayıt sonundaki özetten alındı. Araç ekleme denemesi sayısı ile gerçekten kaydedilen teklif sayısı ayrıldı. `performance.log` için yalnızca bitmiş çağrı satırları sayıldı; tam istek süresi veya tam çağrı sayısı olduğu iddia edilmiyor. Dört kayıtta da `FINAL PAGE CONFIRMED` yok.

Son koşuda LLM süre toplamı duvar saatinin yaklaşık %88,2'si. Yedi `browser_snapshot` çağrısı toplam **0,76 saniye**, altı navigasyon **16,52 saniye**, iki tıklama **5,73 saniye**. Snapshot okumasının doğrudan süresi baskın değil; büyük sayfa metninin LLM'e taşınması ve tekrar eden model kararları ayrı maliyetler. Sağlayıcının kendi web aramaları model çağrısının içinde kalabileceğinden LLM süresinin tamamını yalnızca metin üretimi diye yorumlamamak gerekir.

| Kayıt | Girdi tokenı | Çıktı tokenı | Cache-read tokenı | Girdi eksi cache-read |
| --- | ---: | ---: | ---: | ---: |
| B öncesi | 2.497.419 | 8.547 | 2.376.712 | 120.707 |
| C1 sonrası | 4.203.243 | 21.792 | 1.753.631 | 2.449.612 |
| C2 sonrası | 1.355.676 | 8.292 | 489.888 | 865.788 |

Son sütun yalnızca token farkıdır, parasal maliyet değildir. Daha küçük girdi tek başına daha düşük ücret veya aynı oranda hızlanma kanıtlamıyor. Örneğin C2 kaydında toplam girdi B öncesinden düşükken cache-read dışındaki miktar daha yüksek. Tam istek, model/MCP sürümü ve commit bilgileri kayıt başında birlikte tutulmuyor; bulunan teklif sayısı da değişiyor. Bu koşulardan kontrollü bir hızlanma yüzdesi çıkarılamaz.

Kanıt: [B öncesi özet](../performance_before_b.log), [C1 sonrası özet](../performance_after_c1.log), [C2 sonrası özet](../performance_after_c2.log). Son kayıtta özet 701. satırdan, nihai cevap 722. satırdan başlıyor.

**Öncelikli bulgular**

P1: yanlış sonuç, yetki kontrolünün atlanması veya temel görevin tamamlanamaması. P2: güvenilirlik, maliyet, kullanılabilirlik ve bakım eksikleri. “Yerel doğrulama” gerçek sitede yaşanmış olay anlamına gelmez; ilgili kod yolunun kontrollü girdiye verdiği sonuçtur.

1. **P1 — Mevcut ürün araştırmaları teklif doğrulamasında başarısız oluyor.** Son kayıttaki yedi `research_verify_result` çağrısının tamamı `Identity evidence could not be grounded in the selected offer subtree` ile reddedilmiş. 122. satırdaki örnekte modele ait açıklama cümleleri, sayfadan kopyalanmış kanıt yerine gönderiliyor. Aynı örnekte fiyat metni `6.989 TL` olarak verilmiş, ondalık ayırıcı `.` seçilmiş ve fiyat kanıtında düğüm referansı bulunmuyor; ilk hata çözülse bile başka alanlar da kurala uymuyor. C1 kaydında 14 doğrulama denemesinin tamamı reddedilmiş. **Gerekli iş:** gerçek snapshot ve hatalı quote örneklerini regresyon verisine dönüştürmek; modelin doğru alanı seçmesini kolaylaştıran referans tabanlı kanıt çıkarımı ve alanı açıkça belirten hata yanıtları sağlamak. Doğrulamayı gevşetmek çözüm değil. Konum: [offer_verification.py](../core/research/offer_verification.py), `_excerpt` 81; `validate_quote` 184; [research_tools.py](../core/research/research_tools.py), `research_verify_result` 718.

2. **P1 — Aynı geniş sayfa bölgesindeki farklı teklifler birbirine karıştırılabiliyor.** `offer_ref` için “en küçük teklif kapsayıcısı” isteniyor fakat bu koşul mekanik olarak uygulanmıyor. Kimlik ve satıcının seçilen geniş bölümde bulunması yeterli; fiyatın aynı teklif kartına ait olması her durumda kontrol edilmiyor. Yerel senaryoda L2 ürünü ve Example Provider satıcısı ilk kartta, 100 TL fiyatlı L3 ve başka satıcı ikinci karttaydı. Kök bölüm `offer_ref` verilince **L2, 100 TL olarak doğrulandı**. Bağlantılı başka teklif fiyatı testi mevcut; bağlantısız kardeş kart fiyatı testi yok. **Gerekli iş:** kimlik, satıcı, fiyat, varyant ve ücret düğümlerinin aynı teklif ilişkisine ait olduğunu doğrulamak; belirsiz geniş bölümde doğrulamayı durdurmak. Konum: [offer_verification.py](../core/research/offer_verification.py), 195, 211 ve 271.

3. **P1 — Talep kapsamı ve ücretlerin anlamı doğrulanmıyor.** `criteria` alanı var ama plan oluşturulurken doldurulmuyor; `validate_quote` da bu alanı kullanmıyor. Seyahatte `scope_evidence` için esas kontrol metnin sayfada geçmesi. Üründe `price_scope='total'` için kapsam kanıtı zorunlu bile değil. Yerel kontrolde 20–25 Aralık, dört yetişkin istenirken 10–13 Kasım, iki yetişkin örneği doğrulandı; on ürün talebine tek ürün fiyatı kapsam kanıtı olmadan kabul edildi. Ayrıca `fees_included=True`, ücret kanıtı olarak yalnızca sayfada bulunan satıcı adı verilince kabul edildi. URL eşleştirmesi de yalnızca sabit parametre adlarını tanıyor: farklı `check_in` ve `guests` değerlerine sahip iki URL eşleşti. **Gerekli iş:** kategoriye göre tarih, adet/kişi, yer, varyant ve ücret kapsamını yapılandırmak; alıntının varlığı ile iddiayı desteklemesini ayrı kontrol etmek. Konum: [research_manager.py](../core/research/research_manager.py), 220; [offer_verification.py](../core/research/offer_verification.py), 306; [verification.py](../core/research/verification.py), 11 ve 75.

4. **P1 — Araştırma yapılmadan kaynaklar sonuçsuz veya engelli sayılabiliyor.** `research_record_discovery_attempt` yalnızca modelin yazdığı sorguyu kaydediyor; gözlem ya da gerçekleşmiş araç çağrısı gerekmiyor. `research_complete_source(outcome='blocked')` için boş olmayan açıklama yeterli. Teklif doğrulama engeli de `attempted_url` ve serbest metinle işaretlenebiliyor. Yerel kontrolde hiç tarayıcı gözlemi olmadan bir kaynak `blocked` yapıldı ve araştırma hazır sayıldı. Üç metinsel sorgu kaydedilince `no_results` da kabul edildi. **Gerekli iş:** arama ve erişim hatası kayıtlarını gerçek araç/gözlem kimliklerine bağlamak; modelin kendi kanıt biçim hatasını site erişim engelinden ayırmak. Loglar sağlayıcı içi web aramalarını göstermediği için belirli bir canlı aramanın hiç yapılmadığı sonucuna varılmıyor; doğrulanan açık, durum geçişinin kanıt zorunluluğu olmaması. Konum: [research_tools.py](../core/research/research_tools.py), 259, 494 ve 758; [comparison_state.py](../core/research/comparison_state.py), 509.

5. **P1 — Yarım kalan araştırma sonraki kullanıcı isteğini ele geçiriyor.** `run`, bitmemiş state varsa yeni mesajın niyetini koşulsuz `COMPARISON` yapıyor. İptal, bağımsız yeni görev ve mevcut araştırmaya düzeltme ayrı ele alınmıyor. Yerel sahte model senaryosunda `Merhaba` mesajı üç araştırma çağrısına ve eski araştırmanın raporuna dönüştü. Yeni ürün veya tarih düzeltmesinde eski `target_product`, kaynaklar ve doğrulanmış teklifler de yeniden değerlendirilmeden kalabilir. **Gerekli iş:** devam/düzeltme/yeni görev/iptal ayrımı; kapsam değiştiğinde ilgili tekliflerin ve final kararının geçersizleştirilmesi. Konum: [agent.py](../core/agent.py), 655. Mevcut completion-guard testi `agent.agent.ainvoke` kullanıyor; bu `run` davranışını sınamıyor.

6. **P1 — Tarayıcı güvenlik kontrolü gerçek eylem etkisini güvenilir biçimde belirlemiyor.** `browser_evaluate` içinde `innerText` veya `textContent` bulunması bazı ifadeleri otomatik izinli yapıyor. Yalnızca politika fonksiyonuna verilen `() => document.body.textContent = 'changed'` ifadesi **ALLOW** döndürdü; bu bir okuma değil, atama. `browser_click` hedefi gerçek snapshot düğümüyle eşleştirilmeden modelin açıklamasındaki kelimelere göre değerlendiriliyor. `browser_press_key(key='Enter')` de odaklı formun ne yaptığı bilinmeden izinli. **Gerekli iş:** serbest JavaScript'i bu metin taramasıyla salt okuma saymamak; sabit okuma işlemleri kullanmak, tıklama/form gönderme kararını güncel hedef ve mevcut kullanıcı yetkisiyle ilişkilendirmek. Bu incelemede JavaScript veya tıklama çalıştırılmadı. Konum: [security/policy.py](../core/security/policy.py), 199 ve 426; [security/middleware.py](../core/security/middleware.py), 37.

7. **P2 — Geçmiş küçültme artık yalnızca eski snapshot metnini kapsamıyor.** `prune_old_completed_tool_groups`, sekiz tamamlanmış grup geçilince bütün araç türlerinin eski gruplarını silebiliyor ve normal sohbet isteğinde de uygulanıyor. Yerel örnekte on hesap makinesi sonucunun yalnızca son dördü modele kaldı; silinen sonuçlar `ObservationStore` veya `ComparisonState` içinde değildi. Araştırmada da eski gözlem kimliğini taşıyan grubun tamamen kaldırılması, yalnızca ID kabul eden arşiv okuma aracına erişimi zorlaştırıyor. **Gerekli iş:** küçültmeyi veri türüne ve geri erişim yoluna göre sınırlamak; araştırma dışı sonuçları ve gerekli kimlikleri korumak. Ham geçmiş saklanıyor olması modelin bu bilgilere erişebildiği anlamına gelmiyor. Konum: [browser_context.py](../core/browser_context.py), 148 ve 387; [research_tools.py](../core/research/research_tools.py), 155.

8. **P2 — Kullanıcının belirlediği kaynaklar plana yansımıyor.** `plan_sources` kategoriye ait sabit listeyi döndürüyor. “Sadece Amazon ve Teknosa sitelerinde en ucuz laptopu bul” yerel örneğinde Google Shopping, Trendyol, Hepsiburada, Akakce ve Ciceksepeti seçildi; istenen iki kaynak yoktu. Araştırma araçları planda olmayan kaynağı reddediyor. Doğrudan kaynak/domain kontrolü de yalnızca beş alışveriş sitesinde tanımlı; otel gibi diğer doğrudan kaynaklar aynı kontrolü almıyor. **Gerekli iş:** açık kaynak tercihlerini varsayılanlardan önce uygulamak; kaynak türünü ve domain kurallarını planın parçası yapmak. Konum: [source_planner.py](../core/research/source_planner.py), 270; [research_utils.py](../core/research/research_utils.py), 21 ve 99.

9. **P2 — Tekrarlanan kayıtlar ve tekrar turları hâlâ var.** Aynı tam teklif iki kez eklendiğinde farklı ID'lerle iki sonuç oluştu. Son kayıtta 13 kaynak başlatma çağrısının altısı “already researching”; C1 kaydında 57 çağrının 41'i “already researching”, dokuzu “already finished”. İlerleme mesajı yararlı ancak davranışı zorunlu kılmıyor; aynı anda birden fazla kaynak `researching` olabiliyor. `research_set_offer_url` aynı URL için bile finalizasyonu sıfırlıyor. **Gerekli iş:** tam eşdeğer kayıtlarda idempotent davranış; bağımlı işlemler için açık durum geçişleri; aynı hata ve argüman tekrarını fark eden kontrol. Farklı kaynak, satıcı, tarih veya koşuldaki teklifleri birleştirmemek gerekir. Konum: [comparison_state.py](../core/research/comparison_state.py), 375; [research_tools.py](../core/research/research_tools.py), 704; [progress.py](../core/research/progress.py), 166.

10. **P2 — Uzun işlem, hata ve yeniden devam etme davranışı eksik.** Yirmi devam sınırı toplam LLM/araç çağrısı veya süre sınırı değil; her `ainvoke` içinde birçok tur olabilir. İlerlemesizlik kontrolü de ancak grafik çağrısı bittikten sonra çalışıyor. Uygulamaya ait toplam süre/çağrı bütçesi ve hatada kısmi rapora dönüş yok. `main.py` içinde bir `agent.run` istisnası döngüden çıkarıp tarayıcıyı kapatır. Tarayıcı başlatma ve agent oluşturma ise cleanup `try/finally` bloğundan önce. **Gerekli iş:** aşama bazlı zaman sınırı, kontrollü iptal, başarısızlıkta eldeki veriden kısmi çıktı, hatadan sonra yeni isteğe izin ve başlatma hatasında kaynak temizliği. SDK/kütüphane varsayılan sınırlarının olmadığı iddia edilmiyor; eksik olan uygulamanın kendi davranış sözleşmesi. Konum: [agent.py](../core/agent.py), 694 ve 714; [main.py](../main.py), 22 ve 39.

11. **P2 — Sağlayıcı soyutlaması araçlar ve fallback için tamamlanmamış.** Her sağlayıcıya `{'type': 'web_search'}` ekleniyor; bu dosyanın kendisi bunu OpenAI aracı olarak tanımlıyor. Yüklü Gemini dönüştürücüsüyle ağsız kontrolde bu sözlük Google aramasına değil `MISSING_NAME` adlı işlev bildirimine dönüştü. Gerçek Gemini isteğinin sonucu bu incelemede denenmedi. OpenAI fallback'i ise birincil modelle aynı nesne; alternatif model/sağlayıcı sağlamıyor. Planlama çağrıları agent middleware fallback yolunun dışında. **Gerekli iş:** sağlayıcıya göre araç bildirimi ve ağsız dönüşüm testleri; planlama/araştırma/rapor için tutarlı retry/fallback politikası. Konum: [web_search.py](../core/tools/web_search.py), 1; [agent.py](../core/agent.py), 132; [llm/openai.py](../core/llm/openai.py), 24; [research_manager.py](../core/research/research_manager.py), 70.

12. **P2 — Ölçümler uygulama hatalarını başarı gibi sayabiliyor.** Doğrulama araçları `VERIFICATION BLOCKED` metni döndürdüğü için `on_tool_end` başarılı araç bitişi sayıyor. Son kayıtta yedi doğrulama reddine rağmen araç özeti `errors=0`. Eşzamanlı `print` çağrıları girdi ve çıktıları birbirine karıştırmış; son logun 639–674. satırları örnek. Token bilgisi bazı çağrılarda eksikse tek `token_usage_available` bayrağı kısmi toplamı tam gibi gösterebilir. Kayıtta commit, tam istek, sağlayıcı/model, MCP sürümü, aşamaya göre tokenlar ve doğrulanmış teklif sayısı birlikte yok. **Gerekli iş:** request/run ID içeren atomik olay kayıtları; teknik istisna ile alan doğrulama reddini ayrı saymak; eksik kullanım bilgisini açıkça belirtmek; başarı ölçütünü süreyle birlikte kaydetmek. Konum: [callbacks/timing.py](../core/callbacks/timing.py), 125, 185 ve 190.

13. **P2 — Nihai raporun eksiksizliği yalnızca modele bırakılmış.** Python bütün teklifleri ve URL'leri rapor girdisine ekliyor; çıktı tablo ve bağlantıları deterministik olarak üretmiyor. Son üç tamamlanmış kaydın nihai cevaplarında HTTP(S) bağlantısı yok; son rapor satıcı sayfasının adını yazıyor ancak tıklanabilir teklif URL'si vermiyor. Mevcut rapor testi verinin modele verildiğini kontrol ediyor, modelin kullanıcıya eksiksiz aktardığını değil. **Gerekli iş:** kaynak/teklif/URL/fiyat/durum tablosunu Python'dan üretmek; modele kısa açıklama görevini vermek veya nihai çıktıda zorunlu alan kontrolü yapmak. Konum: [agent.py](../core/agent.py), 518 ve 561; [test_research_workflow.py](../tests/test_research_workflow.py), 481.

**Diğer tamamlanmamış alanlar**

| Alan | Mevcut durum ve etkisi | Konum |
| --- | --- | --- |
| Kanıtı yanlış çıkan teklif | `REJECTED` durumu tanımlı ancak araştırma araçlarıyla bu duruma geçiş yok. Uygunsuz model/oda/uçuş ile erişilemeyen teklif ayrımı eksik. | `comparison_state.py:27`, `research_tools.py:1163` |
| Satın alma/rezervasyon hazırlığı | `requires_staging` daima `False`. Kodda staging araçları var fakat planlama bunları zorunlu kılmıyor. Yeniden etkinleştirilecekse staging sayfası kanıtı ve navigasyonun final sayfa doğrulamasını bozması birlikte çözülmeli. | `research_manager.py:217`, `research_tools.py:1023`, `agent.py:597` |
| İş ilanı ve genel araştırma | Kaynak kategorileri mevcut, fakat ortak doğrulama aracı fiyat/para birimi/satıcı odaklı. Fiyatsız nitel karşılaştırma için ayrı sonuç sözleşmesi yok. | `source_planner.py:143`, `offer_verification.py:16` |
| Bellek ve yeniden başlatma | Tek thread, `InMemorySaver` ve sınırsız ObservationStore var. Model girdisini küçültmek ham geçmişi ve checkpoint birikimini azaltmıyor. Uygulama kapanınca araştırma state'ini geri yükleme yok. Uzun oturum RAM ölçümü bulunmuyor. | `agent.py:77`, `evidence.py:18` |
| Tarayıcı başlangıcı | Her açılışta `npx -y @playwright/mcp@latest`; kullanılan MCP sürümü tekrar üretilebilir biçimde sabit değil. Basit sohbet için de tarayıcı başlatılması bekleniyor. | `browser.py:24`, `main.py:25` |
| Snapshot işlemleri | D1/D2 uygulanmamış: her tarayıcı aracı gözlemi geçersizleştiriyor, eylem çıktısındaki snapshot yeniden kullanılmıyor. `target`/`depth` wrapper'da yok. Son logda snapshot doğrudan süresi düşük olduğundan ilk hız işi olmamalı. | `browser.py:45`, `browser.py:57` |
| Masaüstü kapatma | Benzer isim eşleşmesiyle seçilen süreç `taskkill /IM /T /F` ile zorla kapatılıyor; aynı isimli tüm süreçler ve alt süreçler etkilenebilir, kaydedilmemiş veri kaybolabilir. Mevcut kullanıcı onayı çözümlenen gerçek süreç gösterilmeden alınıyor. | `close_application.py:67`, `close_application.py:112` |
| Kullanıcı deneyimi | İstek sırasında kullanıcıya yönelik aşama özeti ve iptal akışı yok; çok ayrıntılı debug logları var. Loglarda Türkçe karakter bozulması var. İlk kayıttaki UnicodeEncodeError için güncel `main.py` UTF-8 ayarı eklemiş; aynı hatanın hâlâ sürdüğü doğrulanmadı. | `main.py`, `timing.py`, performans kayıtları |
| Kurulum ve bakım | README, `.env.example`, Python/Node kurulum yönergesi ve CI yapılandırması yok. Doğrudan Python bağımlılıkları pinli; transitif bağımlılıkları kilitleyen dosya ve MCP pini yok. | Proje kökü, `requirements.txt` |
| Dosyalar | Eski performans planı ve loglar Git açısından untracked. `.playwright-mcp` içinde 766 dosya, yaklaşık 21,7 MB var; temizleme/rotasyon yok. Bu boyut tek başına mevcut yavaşlığın nedeni değildir. | `git status`, `.playwright-mcp` |

**Eski performans planının güncel karşılığı**

| Adım | Güncel kodda durum | Eksik kabul kanıtı |
| --- | --- | --- |
| A1 | Mesaj/karakter ve süre ölçümü var. | Belgedeki “bekliyor” kaydı eski. |
| A2 | İstek özeti, tokenlar, planlama/araştırma/rapor süreleri ve planlama callback aktarımı var. | Aşama etiketleri, eksik kullanım sayacı, doğrulama retleri ve hata senaryoları tam değil. |
| B | `before_model` completion guard var; gerçek küçük grafik testi mevcut. | Bekleyen/eskimiş/staging durumları ve art arda `run` istekleri için kapsam genişletilmeli. |
| C1 | Snapshot küçültme, arşiv okuma ve tüm eski araç gruplarını budama var. | Son ekleme planın dar kapsamını aşıyor; geri erişim ve normal sohbet kaybı çözülmeli. |
| C2 | Deterministik kısa araştırma durumu her araştırma turuna ekleniyor. | Logda tekrarlar azalmış ama sıfırlanmamış; başarılı araştırma karşılaştırması yok. |
| D1 / D2 | Uygulanmamış. | Mevcut ölçüme göre öncelik daha düşük. |
| E | Bazı bağlam/ilerleme işleri yapılmış. | Tam tekrar kaydı, hata döngüsü ve deterministik rapor eksikleri sürüyor. |
| F | Tamamlanmamış. | Aynı kapsamda başarılı ürün koşusu ve canlı uçuş/otel/kiralama kabul ölçümü yok. |

Eski planın üstündeki commit `217b43e`, ilerleme kaydında A1 bile bekliyor. Bu rapor güncel kodla farkı gösterir; eski planın içeriği bu incelemede değiştirilmedi.

**Kontroller ve test açığı**

`.venv/Scripts/python.exe -B -m unittest discover -s tests`: **59 test geçti**, yaklaşık 1,9 saniye test süresi. `pip check`: bağımlılık tutarsızlığı bulunmadı. `git diff --check`: hata yok. Bu kontroller gerçek site, gerçek model, rezervasyon veya masaüstü eylemi başarısını kanıtlamıyor.

Ek yerel senaryolar yukarıdaki yanlış teklif fiyatı, yanlış tarih/kişi/adet, ilgisiz ücret kanıtı, tarayıcısız kaynak kapatma, yarım araştırmadan sonraki sohbet, kaynak tercihi, URL parametre farkı, araç geçmişinin kaybı, tekrar teklif ve güvenlik kararı açıklarını doğruladı. Bunlar rapor için çalıştırıldı; test veya uygulama dosyaları değiştirilmedi.

Öncelikli eksik testler: gerçek sayfa yapısına benzeyen çok teklifli snapshot; kullanıcının istediği kapsamla uyuşmayan seyahat/ürün; açık ücret belirsizliği; gerçek araç kanıtı olmadan bitiş; iptal/yeni görev/düzeltme; güvenlik kararlarının gerçek hedefle ilişkisi; her iki sağlayıcının araç dönüşümü; MCP hata/biçim ayrıştırması; timeout sonrası kısmi rapor; nihai çıktıda bütün teklif bağlantıları. Mevcut seyahat testleri aynı yapay snapshot şablonunu kullanıyor; tarih ve kişi sayısını talebe karşı doğrulamıyor.

**Önerilen çalışma sırası**

1. Logdaki başarısız quote örnekleri ve yerel yanlış-kabul senaryolarını regresyon verisi olarak sabitle. Önce en az bir gerçek ürün teklifinin doğru kanıtla doğrulanmasını ve yanlış teklif/kapsamın reddedilmesini sağla.
2. Keşif/engel kaydını gerçek araç kanıtına bağla; iptal, yeni istek ve kapsam düzeltmesini state yönetimine ekle. Tarayıcı yetki kontrolündeki doğrulanmış açığı kapat.
3. Geri erişilemeyen veriyi silen geçmiş budamasını sınırla; tekrar teklif ve aynı başarısız işlem turlarını azalt. Sonucu ve teklif bağlantılarını deterministik üret.
4. Ölçüm kaydına görev/sürüm/başarı metriklerini ekle. Aynı model, kaynaklar ve talep koşullarıyla başarılı ürün araştırmasını karşılaştır. D1/D2 ve hedeflenmiş snapshot kararını bu kayda göre ver.
5. Tarih, yer ve kişi koşulları açık uçuş, otel ve araç kiralama akışlarını sırayla doğrula. Ardından sağlayıcı uyumu, hata kurtarma, kalıcılık, kurulum belgeleri ve CI eksiklerini tamamla.

İlk somut hedef: daha kısa sürede biten bir koşudan önce, doğru satıcıya ve tam talep kapsamına ait en az bir teklifin doğrulandığı, kullanıcıya bağlantısıyla ulaştığı ve kaynak kapsamının kanıtlı kaldığı bir koşu elde etmek.
