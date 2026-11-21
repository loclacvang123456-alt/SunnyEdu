# Tài liệu tạo hình và hoạt cảnh game thuyền Sunny Edu

## Phương án hiện tại

Game dùng các ảnh tĩnh hiện có: biển, boong tàu, thủy thủ, pháo, đạn, chỉ huy, mây che, tàu thường `reference/choice-ship-master.png` và tàu hải tặc `choice-ship-pirate.png`. Thuyền nhấp nhô, nghiêng nhẹ; sau khi học sinh chọn đáp án, đạn bay tới, có hiệu ứng nổ và hiện loại thuyền cùng kết quả. Không cần tạo riêng thân tàu, buồm, cột buồm, cờ hoặc các khung hình hoạt ảnh để dùng phiên bản này.

Các prompt và yêu cầu ảnh ở những phần dưới là phương án cũ, lưu lại để tham khảo nếu sau này muốn làm hoạt cảnh chi tiết hơn. Học sinh chơi trong bài luyện tập khi giáo viên bật game; bài kiểm tra dùng giao diện làm bài thông thường.

## 1. Nội dung một câu hỏi

Học sinh là thủy thủ đứng sau một khẩu pháo trên thuyền của mình. Trước mặt có 2 đến 6 thuyền ở xa, tương ứng với 2 đến 6 lựa chọn của câu hỏi. Lá cờ của mọi thuyền đều bị mây che, hình thuyền và mây ban đầu không cho biết đáp án đúng hay sai. Sau khi chọn một đáp án, pháo bắn về phía thuyền đã chọn, đạn bay đến và mây ở thuyền đó tan đi.

Nếu đáp án đúng, hiện cờ hải tặc và thuyền đó chìm xuống nước theo cách hoạt hình nhẹ nhàng. Nếu đáp án sai, hiện cờ phe mình, thuyền đó chìm và người chỉ huy tức giận nhảy cẫng lên theo cách hài hước, không làm học sinh sợ. Sau hoạt cảnh, học sinh thấy kết quả và hướng dẫn tiếp theo theo quy tắc bài tập đã được giáo viên cấu hình.

Đây là cảnh trò chơi tưởng tượng dành cho trẻ em: không có người bị thương, máu, lửa cháy dữ dội, tiếng hét hay chi tiết bạo lực. Không dùng hình xương sọ đáng sợ. Lá cờ hải tặc có thể dùng hình đầu lâu được cách điệu hiền lành hoặc một biểu tượng hải tặc đơn giản; lá cờ phe mình dùng biểu tượng mặt trời đơn giản. Các biểu tượng này không phải logo chính thức Sunny Edu.

Mỗi câu hỏi chỉ có một đáp án đúng. Nếu loại câu cho phép nhiều đáp án, không dùng cảnh bắn pháo một lần này cho đến khi quy tắc chọn và chấm được thiết kế riêng. Game không tự suy đoán đáp án từ màu sắc, hình dạng thuyền hay vị trí: hệ thống quyết định kết quả của lựa chọn sau khi nhận câu trả lời.

## 2. Phong cách hình ảnh

Dùng cùng hướng minh họa của website Sunny Edu trong `chi-tiet-hinh-anh-website-tieng-anh.md`: minh họa kỹ thuật số 2D hiện đại, nét mềm gọn, màu tươi vừa phải, gần gũi với học sinh Việt Nam. Không dùng ảnh chụp, 3D bóng nhựa, pixel art, anime hoặc nét phác thảo. Dùng bảng màu tham khảo: xanh biển `#3C8EAE`, xanh dương `#2563EB`, xanh nhạt `#DBEAFE`, vàng nắng `#FDE68A`, nâu gỗ `#A96F45`, kem `#FFFBF2` và xanh lá dịu `#3F786D`. Các mã màu định hướng, không yêu cầu Gemini khớp từng pixel.

Bối cảnh là biển ngày nắng, thời kỳ thuyền buồm, có mây trắng, thuyền gỗ và buồm vải. Ánh sáng ban ngày đi từ góc trên bên trái, bóng đổ mềm xuống dưới bên phải. Dùng ít chi tiết nền để học sinh dễ nhìn đáp án. Khuôn mặt nhân vật có nét biểu cảm dễ đọc, tỷ lệ cơ thể tự nhiên theo phong cách minh họa, không cường điệu đến mức đáng sợ.

Góc nhìn chính: học sinh nhìn từ phía sau và hơi cao hơn một chút, thấy một phần boong thuyền và khẩu pháo hướng ra biển. Người chỉ huy đứng ở mép phải boong, có thể nhìn thấy biểu cảm khi phản ứng. Các thuyền đáp án ở xa, cùng góc nhìn và cùng tỷ lệ. Khi tạo hình, không vẽ chữ, tên học sinh, điểm, câu hỏi, đáp án, số, logo, watermark, nút bấm hoặc ảnh chụp giao diện; chữ và nút được giao diện website đặt riêng sau này.

## 3. Cách dùng tài liệu này với Gemini

1. Tạo một ảnh tham chiếu hoàn chỉnh theo mục 4. Chọn một phiên bản làm chuẩn về màu, góc nhìn, ánh sáng, kích thước tương đối và nhân vật. Ảnh này chỉ làm mẫu, không dùng làm nền game cuối cùng vì các bộ phận đã bị dính vào nhau.
2. Gửi lại ảnh tham chiếu cùng mỗi prompt trong mục 6. Yêu cầu Gemini tạo từng tệp hình riêng, cùng nét vẽ, không tự đổi thiết kế của các nhân vật hoặc thuyền. Nếu không đính kèm ảnh tham chiếu được, dán prompt phong cách chung trước từng prompt.
3. Tạo các cảnh và vật thể tách rời: bầu trời, biển, boong, pháo, thuyền, cờ, mây, đạn, nước bắn và các phần cơ thể của chỉ huy. Không nhờ Gemini tạo một ảnh chụp hoàn chỉnh có sẵn chữ hoặc giao diện trò chơi.
4. Đối với nhân vật và vật thể có khớp, ảnh bộ phận phải có nền trong suốt thật. Nếu công cụ không xuất được nền trong suốt, yêu cầu nền màu phẳng đồng nhất, không có hoa văn hay bóng nền, sau đó người thiết kế tách nền và kiểm tra mép. Ô caro vẽ trong ảnh không phải nền trong suốt.
5. Kích thước dưới đây là mục tiêu cho người dựng. Nếu Gemini không chọn được pixel chính xác, giữ tỷ lệ rồi xuất độ phân giải cao; người thiết kế có thể chuẩn hóa file sau. Không kéo dãn lệch tỷ lệ. Gemini có thể tạo sai số lượng, lẫn khớp hoặc thay đổi thiết kế, vì vậy phải xem từng file, sửa và xuất lại trước khi lắp vào game.
6. Bộ ảnh và khung hình đều do Gemini hoặc người thiết kế tạo, không vẽ lại nhân vật, thuyền hay khung cảnh bằng hình khối lập trình. Lập trình viên vẫn cần lắp các ảnh, chuyển trạng thái và đồng bộ hình với thao tác bấm; việc này không tạo lại phong cách hội họa bằng code.
7. Lưu bản gốc và bản đã chuẩn hóa riêng. Không đăng hình lên dịch vụ công khai. Chỉ sử dụng hình có quyền dùng phù hợp, kể cả khi chỉnh sửa bằng công cụ khác.

## 4. Prompt ảnh tham chiếu hoàn chỉnh

Tỷ lệ 16:9, mục tiêu 1920 × 1080 px. Đây là ảnh duyệt phong cách, không phải sprite và không dùng để tiết lộ đáp án.

```text
Tạo một ảnh tham chiếu minh họa 2D cho trò chơi trắc nghiệm tiếng Anh của trẻ em Việt Nam. Góc nhìn từ sau một thủy thủ nhí đang đứng trên boong một con thuyền gỗ, hơi nhìn từ trên xuống. Một khẩu pháo gỗ cách điệu nằm ở giữa phần dưới, hướng ra biển. Nhân vật thủy thủ nhìn từ phía sau đứng gần bên trái pháo, mặc áo xanh dương và đội mũ thủy thủ. Ở gần mép phải boong có một người chỉ huy thân thiện mặc áo xanh lá đậm, áo khoác nâu nhạt, mũ thuyền trưởng và khăn quàng vàng. Phía xa ngoài biển có bốn con thuyền buồm giống hệt nhau về màu sắc, hình dáng và kích thước, xếp trên cùng đường chân trời. Cờ của từng thuyền đều bị một đám mây trắng che hoàn toàn; không nhìn thấy biểu tượng cờ và không có thuyền nào trông đáng ngờ hơn thuyền khác. Bầu trời sáng và biển xanh, ánh sáng dịu từ trên trái, nét vẽ mềm, gọn, 2D hiện đại phù hợp trẻ em, cùng phong cách giáo dục Sunny Edu. Chừa phần trên và phần giữa ảnh thoáng để website tự đặt câu hỏi và đáp án. Không chữ, không con số, không logo, không nút giao diện, không watermark, không máu hay người bị thương. Khung ngang 16:9, mục tiêu 1920 × 1080 px.
```

Khi duyệt, nhìn rõ khẩu pháo, nhân vật chỉ huy và bốn thuyền; tất cả thuyền vẫn giống nhau trước khi lộ cờ. Nếu ảnh mẫu làm các thuyền quá nhỏ để nhìn trên điện thoại, yêu cầu phiên bản có thuyền lớn hơn và ít chi tiết nền hơn. Không lấy tỉ lệ trong một ảnh mẫu làm giới hạn duy nhất cho giao diện.

## 5. Quy chuẩn chung cho từng lớp ảnh

Các kích thước sau là kích thước khung thiết kế, không phải bảo đảm pixel do Gemini xuất chính xác. Giữ góc nhìn, màu, hướng sáng và tỷ lệ đã duyệt ở ảnh tham chiếu. Mọi file phải tách riêng; không gộp nhiều vật thể thành một ảnh nền khi các vật đó cần di chuyển độc lập.

| Nhóm | File đề xuất | Kích thước mục tiêu | Nội dung và nền |
|---|---|---|---|
| Bầu trời | `sea-sky.png` | 1920 × 1080 | Bầu trời và đường chân trời, không thuyền, không nhân vật. |
| Biển | `sea-water-back.png` | 1920 × 1080 | Lớp nước ở xa, nền trong suốt. |
| Boong | `player-deck.png` | 1920 × 1080 | Phần mép boong phía trước, không nhân vật hoặc pháo, trong suốt ngoài vùng boong. |
| Sóng trước | `sea-water-front.png` | 1920 × 1080 | Lớp sóng ở tiền cảnh có thể che phần dưới thân thuyền khi thuyền chìm, nền trong suốt. |
| Pháo | `cannon-base.png`, `cannon-barrel.png` | 1024 × 1024 mỗi file | Giá pháo và nòng pháo riêng, nền trong suốt. |
| Đạn | `cannonball.png` | 512 × 512 | Một viên đạn riêng, nền trong suốt. |
| Hiệu ứng pháo | `cannon-smoke-01.png` đến `cannon-smoke-04.png` | 512 × 512 mỗi frame | Bốn khung khói không lửa mạnh, nền trong suốt, cùng khung đặt. |
| Thuyền đáp án | `choice-ship-hull.png`, `choice-ship-sail.png`, `choice-ship-mast.png` | 1024 × 1024 mỗi file | Một thiết kế thuyền dùng lại cho mọi lựa chọn; thân, buồm và cột riêng, nền trong suốt. |
| Cờ và mây | `flag-covered-cloud.png`, `flag-friendly.png`, `flag-pirate.png` | 512 × 512 mỗi file | Một mây che, một cờ phe mình và một cờ hải tặc, mỗi cái riêng, nền trong suốt. |
| Thủy thủ nhí | `sailor-back.png` | 1024 × 1024 | Một nhân vật nhìn từ phía sau, nền trong suốt; chỉ cần ảnh đứng yên ở bản đầu. |
| Chỉ huy | `commander-master.png`, `commander-*.png` | 1024 × 1024 mỗi file | Một bản mẫu toàn thân để duyệt và các bộ phận riêng cùng khung, nền trong suốt. |
| Nước bắn | `splash-01.png` đến `splash-04.png` | 512 × 512 mỗi frame | Bốn khung nước bắn nhẹ, nền trong suốt, cùng vị trí. |

Không ép Gemini tự dựng một tấm sprite sheet chứa nhiều khung nếu các khung bị lệch. Tạo từng frame thành file riêng, sau đó người thiết kế kiểm tra và đóng gói nếu cần. File ảnh master toàn cảnh và nhân vật master không được sử dụng như một lớp game thay cho các phần đã tách.

### Vị trí theo lớp

Theo thứ tự từ xa đến gần: bầu trời, biển xa, thuyền đáp án, cột và buồm, cờ, mây che cờ, lớp nước trước thuyền, boong người chơi, thủy thủ, giá pháo và nòng pháo, chỉ huy, đạn và hiệu ứng. Người làm giao diện có thể đổi thứ tự cục bộ để nòng pháo hoặc tay nằm đúng trước/sau thân người, nhưng không được làm lộ cờ qua lớp mây trước khi chọn.

Khung 1920 × 1080 chỉ là thiết kế gốc. Vùng nội dung cần nhìn thấy nằm trong khoảng 10–90% chiều ngang và 8–90% chiều cao. Khi màn hình hẹp, phải điều chỉnh bố cục và thu/phóng các lớp để câu hỏi, đáp án, pháo và thuyền đã chọn vẫn nhìn thấy. Không cắt giữa ảnh desktop làm mất đáp án hoặc kéo méo tất cả hình. Nếu cần cảnh dọc, tạo lại nền và boong theo tỷ lệ 4:5 với cùng phong cách; không yêu cầu Gemini tự thêm câu hỏi vào ảnh.

### Quy tắc khớp nối

- Dựng mẫu chỉ huy toàn thân ở giữa khung 1024 × 1024 trước. Giữ nguyên khung, tỷ lệ, góc nhìn và vị trí gốc cho tất cả các file bộ phận. Không tự phóng to từng bộ phận để chiếm toàn khung.
- Khi tách nhân vật, cần các lớp: thân và hông, đầu có cổ, hai cánh tay trên, hai cẳng tay kèm bàn tay, hai đùi, hai cẳng chân kèm bàn chân, mũ và tóc phía trước nếu tóc che mặt. Bên trái/phải được đặt tên theo phía người xem, không theo cơ thể nhân vật.
- Ảnh mỗi bộ phận có thêm phần màu bên dưới tại vị trí khớp vai, khuỷu, hông và đầu gối để khi xoay không bị hở nền. Không cắt đúng mép đường viền khớp. Người thiết kế xác nhận vị trí điểm xoay trên file gốc sau khi duyệt; Gemini không bảo đảm khớp chính xác chỉ nhờ prompt.
- Đầu và thân cần cùng hướng nhìn. Có thể làm 3 gương mặt thay thế cùng vị trí: bình thường, vui, tức giận hài hước; không thay đổi hình dáng đầu giữa các tệp. Mỗi gương mặt nằm trên cùng khung đầu, khớp cổ không đổi.
- Thân, cột buồm, buồm và cờ của thuyền giữ cùng hệ tọa độ ở mọi tệp. Cờ, mây và điểm gắn trên cột được duyệt bằng hình chồng thử; mây phải che toàn bộ hai kiểu cờ ở mọi khung trước khi được mở.
- Các hiệu ứng theo chuỗi phải có kích thước khung bằng nhau và cùng điểm neo. Không để viên đạn hoặc vụ nước bắn tự dịch vị trí trong từng ảnh khi yêu cầu chúng đứng yên trong cùng khung.

## 6. Các prompt tạo từng bộ phận

Gửi prompt ảnh tham chiếu ở mục 4 trước, sau đó chọn một ảnh chuẩn. Với mỗi prompt dưới đây, đính kèm ảnh chuẩn nếu Gemini hỗ trợ. Mỗi prompt chỉ tạo một file trừ khi có ghi rõ yêu cầu từng frame riêng.

### A. Bầu trời, biển và boong

**A1. Bầu trời**

```text
Dựa trên ảnh game thuyền Sunny Edu đính kèm, tạo riêng một lớp nền bầu trời và đường chân trời, khung ngang 16:9, mục tiêu 1920 × 1080. Góc nhìn, ánh sáng và màu phải giống ảnh tham chiếu. Bầu trời xanh rất nhạt ở phía trên, sáng hơn gần đường chân trời ở khoảng 48% chiều cao. Có đúng ba cụm mây xa nhỏ ở phần trên, không có mây tại các vị trí che cờ. Không có biển tiền cảnh, thuyền, boong, pháo, người, chữ hay giao diện. Bề mặt sạch và đủ thoáng để các lớp ảnh khác đặt lên trên.
```

**A2. Biển phía sau thuyền**

```text
Dựa trên ảnh tham chiếu, tạo riêng lớp mặt biển xa 1920 × 1080 với nền trong suốt. Chỉ vẽ nước từ đường chân trời ở khoảng 48% chiều cao trở xuống, màu xanh biển dịu với gợn sóng mềm và thưa. Chừa trong suốt phần bầu trời phía trên. Không có thuyền, boong, cờ, mây che cờ, nhân vật, pháo, chữ hay giao diện. Giữ cùng phối cảnh và ánh sáng từ trên trái.
```

**A3. Boong thuyền của người chơi**

```text
Dựa trên ảnh tham chiếu, tạo riêng một lớp boong thuyền gỗ của người chơi, kích thước khung 1920 × 1080, nền trong suốt. Boong chiếm khoảng 28% chiều cao ở phía dưới khung hình; nhìn từ phía sau và hơi từ trên xuống về phía biển. Có ván gỗ và một lan can thấp ở mép xa, màu gỗ nâu ấm, chi tiết vừa phải. Không vẽ pháo, đạn, thuyền khác, cờ, người, biển, chữ hoặc giao diện. Các vùng ngoài boong phải trong suốt thật.
```

**A4. Sóng che phần thân khi chìm**

```text
Dựa trên ảnh tham chiếu, tạo riêng một dải sóng nhẹ 1920 × 1080 nền trong suốt. Dải sóng ở vùng biển xa khoảng từ 55% đến 75% chiều cao khung hình, có chỗ bằng phẳng đủ dài để che dần phần dưới thân các thuyền đáp án khi di chuyển xuống. Chỉ có nước và bọt sóng nhỏ, không có thuyền, cờ, mây, người hay chữ. Dùng đúng màu và phối cảnh của lớp mặt biển đã tạo.
```

### B. Pháo và đạn

**B1. Giá pháo**

```text
Dựa trên ảnh tham chiếu, tạo riêng giá đỡ của một khẩu pháo đặt trên boong thuyền. Khung vuông 1024 × 1024, nền trong suốt, góc nhìn từ sau và hơi cao. Giá bằng gỗ nâu ấm, có hai bánh gỗ nhìn thấy một phần. Không vẽ nòng pháo, đạn, người, sàn, chữ hay vật khác. Đặt giá ở chính giữa phía dưới, phần gắn nòng để trống nhưng có bề mặt đầy đủ để nòng được đặt chồng sau.
```

**B2. Nòng pháo**

```text
Dựa trên giá pháo và ảnh tham chiếu đã gửi, tạo riêng một nòng pháo màu xanh xám đậm, phong cách hoạt hình thân thiện. Khung 1024 × 1024, nền trong suốt và cùng góc nhìn từ sau hơi cao. Đặt nòng sao cho phần gốc khớp với giá pháo ở giữa phía dưới và miệng hướng về phía trên của khung. Không vẽ giá, bánh, đạn, khói, người, chữ hay vật khác. Giữ phần gốc nòng có đủ hình để xoay nhẹ mà không hở.
```

**B3. Một viên đạn pháo**

```text
Tạo một viên đạn pháo hình cầu hoạt hình màu xám xanh đậm, một vật thể duy nhất, khung 512 × 512 nền trong suốt. Có một điểm sáng dịu ở góc trên trái, không có mặt, không lửa, không chữ và không vệt bay. Viên đạn nằm chính giữa, chiếm khoảng 30% bề ngang khung. Phong cách giống khẩu pháo tham chiếu.
```

**B4. Khói pháo bốn frame**

```text
Tạo riêng từng file cho bốn frame khói pháo hoạt hình trẻ em, cùng khung 512 × 512 nền trong suốt, cùng một điểm xuất phát ở giữa phía dưới và cùng nét vẽ với khẩu pháo tham chiếu. Frame 01 là một đám khói tròn rất nhỏ, frame 02 là đám khói lớn hơn, frame 03 khói nở rộng và nhạt hơn, frame 04 khói tan thành hai cụm nhỏ rất nhạt. Không có nòng pháo, đạn, lửa, người hoặc chữ trong bất kỳ frame nào. Xuất bốn ảnh riêng và giữ nguyên vị trí khung, không ghép bốn ảnh thành một.
```

### C. Một mẫu thuyền dùng cho mọi đáp án

**C1. Duyệt mẫu trước khi tách**

```text
Dựa trên ảnh tham chiếu, tạo một con thuyền đáp án duy nhất nhìn từ phía người chơi trên biển, góc nhìn giống bốn thuyền xa trong ảnh. Thuyền gỗ nhỏ, một thân thuyền nâu, một cột buồm, một buồm màu kem và một cờ trống chưa có biểu tượng. Hình vui, không làm thuyền có vẻ hiền hay dữ để tiết lộ đáp án. Khung 1024 × 1024 nền trong suốt, vật thể ở giữa và chừa 15% lề, không có biển, mây, người hay chữ. Đây là bản mẫu để duyệt và dùng làm tham chiếu cho các lớp tách tiếp theo.
```

**C2. Thân thuyền**

```text
Từ mẫu thuyền đáp án đã duyệt, tạo riêng thân thuyền gỗ nâu. Giữ nguyên tỷ lệ, vị trí và góc nhìn trong cùng khung 1024 × 1024 nền trong suốt. Không có cột, buồm, cờ, mây, nước hoặc người. Vẽ đầy đủ phần gỗ phía sau chỗ cột buồm được lắp, không để thủng nền tại khớp.
```

**C3. Cột buồm**

```text
Từ mẫu thuyền đáp án đã duyệt, tạo riêng một cột buồm trong cùng khung 1024 × 1024 nền trong suốt, giữ nguyên vị trí và góc nhìn. Không có thân thuyền, buồm, cờ, mây hay nước. Chừa đủ phần thân cột tại điểm lắp buồm và cờ, không tạo lỗ trong suốt ở điểm nối.
```

**C4. Buồm**

```text
Từ mẫu thuyền đáp án đã duyệt, tạo riêng một tấm buồm màu kem trong cùng khung 1024 × 1024 nền trong suốt, giữ nguyên tỷ lệ, vị trí, góc nhìn và ánh sáng. Không có thân thuyền, cột, cờ, mây, nước, chữ hay hình vẽ trên buồm. Mép buồm rõ và không bị cắt.
```

### D. Cờ và mây che

Hai ảnh cờ phải cùng kích thước khung, điểm gắn vào cột, góc nghiêng, kích thước cờ và độ phồng của vải. Ở trạng thái ban đầu, một lớp mây giống nhau che kín toàn bộ cờ của tất cả thuyền. Không tạo cờ phe mình trông đã lộ ra hay khiến hình mây khác nhau theo đáp án.

**D1. Cờ phe mình**

```text
Tạo riêng một lá cờ nhỏ của phe thủy thủ thân thiện theo ảnh thuyền tham chiếu. Khung 512 × 512 nền trong suốt, một lá cờ vải màu xanh dương nhạt, một biểu tượng mặt trời vàng đơn giản ở chính giữa. Cờ nhìn nghiêng và bay nhẹ về phía phải; mép gắn cột ở bên trái. Không vẽ cột, thuyền, mây, nước, chữ, số hay logo Sunny Edu. Chừa 20% lề để không cắt mép cờ.
```

**D2. Cờ hải tặc**

```text
Tạo riêng một lá cờ hải tặc hoạt hình thân thiện cho trẻ em, cùng khung 512 × 512, cùng vị trí, tỷ lệ, điểm gắn, góc nghiêng và độ phồng vải như ảnh cờ phe mình đính kèm. Cờ màu xanh đậm và có một biểu tượng hải tặc đơn giản ở giữa, tạo hình hiền, không đáng sợ. Không có máu, không có chữ, số hoặc logo. Không vẽ cột, thuyền, mây, nước hay người. Nền trong suốt thật.
```

**D3. Mây che cờ**

```text
Tạo riêng một đám mây trắng mềm để che cờ thuyền trong game, khung 512 × 512 nền trong suốt. Đám mây nằm ở cùng vị trí cờ trong các ảnh tham chiếu, lớn hơn hình lá cờ khoảng 20% ở mỗi phía để che kín cả hai thiết kế cờ; vẫn chừa lề trong khung ảnh. Mây có hình dạng chung, không mang dấu hiệu đúng hay sai. Không có thuyền, cột, cờ, người, chữ, số hoặc biểu tượng khác. Giữ ánh sáng và phong cách 2D của bộ game.
```

**D4. Mây tan bốn frame**

```text
Dựa trên ảnh mây che cờ đã duyệt, tạo bốn frame riêng trong cùng khung 512 × 512 nền trong suốt. Frame 01 giống hệt đám mây che kín ban đầu; frame 02 mây tách thành hai phần nhưng vẫn không vẽ cờ; frame 03 hai phần mây di chuyển ra hai bên và mờ đi; frame 04 chỉ còn vài vệt mây rất nhạt. Giữ cùng điểm neo, kích thước khung và hướng sáng. Không vẽ cờ, thuyền, nước, chữ hay số trong các frame. Xuất từng frame thành file riêng.
```

### E. Thủy thủ nhìn từ phía sau

```text
Dựa trên nhân vật thủy thủ trong ảnh tham chiếu, tạo riêng một thủy thủ nhí châu Á nhìn từ phía sau, đứng yên, hai chân tự nhiên, tay để hai bên, mặc áo xanh dương và đội mũ thủy thủ. Khung 1024 × 1024 nền trong suốt, toàn thân nằm giữa, chừa 15% lề, góc nhìn hơi cao như ảnh gốc. Không có boong, pháo, biển, thuyền, cờ, chữ, số hoặc vật khác. Nhân vật thân thiện và không cầm vũ khí.
```

### F. Chỉ huy và các bộ phận để chuyển động

Tạo bản toàn thân trước để chốt tạo hình. Sau đó dùng bản đó làm ảnh tham chiếu cho mọi bộ phận và biểu cảm. Chỉ huy phản ứng hài hước khi chọn sai; không có lời xúc phạm hoặc hình phạt.

**F1. Nhân vật mẫu toàn thân**

```text
Tạo mẫu nhân vật chỉ huy thuyền cho game tiếng Anh trẻ em, khung 1024 × 1024 nền trong suốt. Một người trưởng thành châu Á thân thiện, mặc áo xanh lá đậm, áo khoác nâu nhạt, khăn quàng vàng, quần xanh đậm, giày nâu và mũ thuyền trưởng đơn giản không có logo. Toàn thân nhìn nghiêng ba phần tư về bên trái, tay và chân hơi tách khỏi thân để dễ tách lớp, nét mặt bình thường. Nhân vật chiếm khoảng 70% chiều cao, đứng ở giữa khung, chừa khoảng trống bốn bên. Cùng phong cách 2D, ánh sáng và bảng màu của ảnh game tham chiếu. Không vẽ boong, pháo, biển, người khác, chữ, số hoặc watermark.
```

**F2. Các bộ phận riêng**

```text
Dùng đúng nhân vật chỉ huy mẫu đính kèm, tạo từng file riêng với cùng khung 1024 × 1024 nền trong suốt và giữ nguyên kích thước, vị trí của nhân vật gốc; không tự phóng to từng phần. Cần các file: thân và hông; đầu có cổ; cánh tay trên bên trái ảnh; cánh tay trên bên phải ảnh; cẳng tay và bàn tay bên trái ảnh; cẳng tay và bàn tay bên phải ảnh; đùi bên trái ảnh; đùi bên phải ảnh; cẳng chân và bàn chân bên trái ảnh; cẳng chân và bàn chân bên phải ảnh; mũ. Mỗi file chỉ có một phần tương ứng. Ở vai, khuỷu, hông và đầu gối, vẽ thêm phần bị che bên dưới để khi xoay các lớp không lộ lỗ trống. Giữ đúng màu áo, viền, ánh sáng, hướng nhìn và tạo hình gốc. Không thêm vật, không thêm chữ, không xuất thành một sprite sheet.
```

Nếu Gemini không thể xuất nhiều file trong một lần, gửi lại prompt từng phần, thay danh sách bằng tên một bộ phận. Không cắt bộ phận từ ảnh có nền phức tạp hoặc có tay chân chồng lên nhau rồi coi là đã sẵn sàng; phải ghép thử và sửa mép che.

**F3. Ba biểu cảm trên cùng đầu**

```text
Dùng đúng đầu và mũ của nhân vật chỉ huy mẫu đính kèm. Tạo ba ảnh đầu riêng, cùng khung 1024 × 1024, cùng vị trí cổ, mắt, mũ và tỷ lệ; nền trong suốt. Ảnh 1: nét mặt bình thường, quan sát. Ảnh 2: vui nhẹ khi học sinh chọn đúng. Ảnh 3: cau mày, miệng mở nhẹ và tức giận hài hước khi học sinh chọn sai, không đáng sợ. Không thêm thân, tay, chân, thuyền, chữ hay biểu tượng. Không làm thay đổi kiểu tóc, trang phục, ánh sáng hoặc góc nhìn giữa ba ảnh.
```

**F4. Frame nhảy cẫng khi sai**

Người dựng có thể tạo hoạt cảnh từ các phần đã kiểm tra ở F2–F3. Nếu cách ghép bộ phận làm khớp trông giả, yêu cầu Gemini hoặc họa sĩ tạo năm ảnh toàn thân riêng theo prompt sau, tất cả cùng nhân vật, cùng khung và cùng vị trí tiếp đất. Không dùng hai cách cùng một lúc khiến nhân vật bị nhân đôi.

```text
Dựa trên nhân vật chỉ huy đã duyệt, tạo năm ảnh toàn thân riêng cho một lần nhảy tức giận hài hước. Tất cả ảnh cùng khung 1024 × 1024 nền trong suốt, cùng tỷ lệ, góc nhìn, quần áo và điểm tiếp đất ở giữa phía dưới. Frame 01 đứng và cau mày; frame 02 hơi khuỵu gối; frame 03 nhảy lên, hai tay đưa lên nhưng vẫn trong khung; frame 04 hạ xuống; frame 05 đứng lại với vẻ cau mày nhẹ. Không biến đổi kiểu mặt hoặc trang phục, không dọa nạt, không người khác, không chữ, không boong thuyền. Xuất năm file riêng, không ghép sprite sheet.
```

### G. Nước bắn và thuyền chìm

Khi chìm, dùng cùng một thuyền đã hiện cờ và di chuyển phần thuyền xuống sau lớp sóng. Nếu dùng các frame vẽ sẵn, chúng phải lấy từ cùng thiết kế thuyền, không tạo một thuyền mới ở mỗi frame. Hoạt cảnh không có người hoặc sinh vật bị thương. Hiệu ứng được phát sau khi có kết quả của lựa chọn.

**G1. Bốn frame nước bắn**

```text
Tạo bốn frame nước bắn hoạt hình nhẹ khi một thuyền gỗ hạ xuống nước, theo phong cách game Sunny Edu tham chiếu. Mỗi frame là một file riêng khung 512 × 512 nền trong suốt, cùng điểm neo ở chính giữa phía dưới. Frame 01 là gợn nước nhỏ, frame 02 có hai tia nước thấp, frame 03 là bọt nước tỏa rộng hơn, frame 04 chỉ còn gợn nước nhạt. Không vẽ thuyền, người, máu, lửa, chữ hay số. Giữ cùng màu nước và hướng sáng của nền biển.
```

**G2. Khung thuyền chìm nếu cần vẽ sẵn**

```text
Dựa chính xác trên mẫu thuyền đáp án đã duyệt và cùng một mẫu cờ được chọn, tạo bốn hình riêng của cùng một con thuyền đang hạ dần xuống mặt nước: còn nguyên, thấp xuống một phần tư thân, thấp xuống một nửa thân, chỉ còn phần trên buồm. Khung mỗi ảnh 1024 × 1024, giữ cùng kích thước, góc nhìn và vị trí ngang, không thay đổi hình dạng thuyền, buồm hay cờ. Phần bị che bởi mặt nước phải trong suốt để ghép với lớp biển trong game. Không vẽ nhân vật, máu, lửa, chữ, số hoặc các thuyền khác.
```

Dùng prompt G2 hai lần với ảnh cờ phe mình và cờ hải tặc tương ứng nếu cách dựng cần hình thuyền và cờ dính sẵn. Cách ưu tiên vẫn là giữ cờ tách riêng để cùng một thuyền có thể dùng cho mọi lựa chọn và tránh để lộ đáp án trước khi chọn.

## 7. Bảng tên file của nhân vật và frame

| Loại | Tên file |
|---|---|
| Mẫu chỉ huy | `commander-master.png` |
| Thân và hông | `commander-body.png` |
| Đầu bình thường, vui, tức giận hài hước | `commander-head-neutral.png`, `commander-head-happy.png`, `commander-head-angry.png` |
| Cánh tay trên | `commander-upper-arm-left.png`, `commander-upper-arm-right.png` |
| Cẳng tay và bàn tay | `commander-forearm-left.png`, `commander-forearm-right.png` |
| Đùi | `commander-thigh-left.png`, `commander-thigh-right.png` |
| Cẳng chân và bàn chân | `commander-shin-left.png`, `commander-shin-right.png` |
| Mũ | `commander-hat.png` |
| Frame nhảy nếu dùng ảnh toàn thân | `commander-jump-01.png` đến `commander-jump-05.png` |
| Frame mây tan | `cloud-reveal-01.png` đến `cloud-reveal-04.png` |
| Frame nước bắn | `splash-01.png` đến `splash-04.png` |

“Left” và “right” trong tên file tính theo phía người xem. Nếu tóc được tách riêng do che mặt, đặt tên `commander-hair-front.png` và ghi rõ vị trí xếp lớp. Nếu phần đầu trong các file biểu cảm đã chứa mũ, không dùng thêm `commander-hat.png` ở lần dựng đó.

## 8. Quy tắc ghép vào luồng học sinh

1. Khi mở câu mới, giao diện hiển thị câu hỏi và các đáp án là thành phần thật của website, không phải chữ vẽ trong ảnh. Mỗi đáp án gắn một thuyền nhìn giống nhau, với một cờ bị lớp mây che hoàn toàn. Cần thể hiện sự liên kết rõ giữa đáp án và thuyền trên cả điện thoại lẫn máy tính.
2. Học sinh chọn một đáp án bằng chạm, chuột hoặc bàn phím. Hệ thống chỉ ghi nhận một thao tác chọn cho một lần trả lời. Sau khi xác nhận lựa chọn, khóa lựa chọn trong lúc gửi và chờ kết quả. Không dùng animation làm bằng chứng rằng câu trả lời đã lưu.
3. Sau khi máy chủ xác nhận và trả kết quả được phép hiển thị, pháo mới bắn, đạn bay đến đúng thuyền đã chọn, mây tan, hiện cờ phù hợp rồi thuyền hạ xuống. Nếu sai, chỉ huy thực hiện một lần nhảy tức giận hài hước; nếu đúng, có thể hiện biểu cảm vui. Không hiện cờ các thuyền còn lại, trừ khi chính sách bài tập cho phép công bố đáp án.
4. Phần hình, nhạc và chuyển động chỉ minh họa trạng thái do máy chủ trả về. Không gửi đáp án đúng hoặc loại cờ của từng thuyền vào trình duyệt trước khi học sinh chọn; file cờ chung có thể được tải trước nhưng không gán cho lựa chọn cụ thể trước kết quả. Không đánh dấu đáp án đúng qua tên tệp, vị trí, màu thuyền, dữ liệu HTML hoặc nội dung dành cho trình đọc màn hình.
5. Nếu lưu thất bại hoặc mạng mất, dừng trước bước lộ cờ và báo học sinh thử lại. Không tự đổi kết quả hoặc tạo thêm lần trả lời khi người dùng bấm lại. Sau khi có kết quả, cho học sinh tiếp tục sang câu kế tiếp theo quy tắc bài tập và lịch sử đã lưu.
6. Nếu giáo viên cấu hình không cho xem đúng sai ngay, không làm cảnh cờ và thuyền tiết lộ kết quả trong lúc làm. Chỉ hiện pháo bắn trúng mây rồi thuyền vẫn ở trạng thái trung tính; kết quả được xem khi đến thời điểm công bố. Với bài kiểm tra, dùng giao diện nghiêm túc đã quy định thay vì cảnh game.
7. Không bắt buộc học sinh phải nghe âm thanh. Nếu sau này có âm thanh, có nút tắt, không tự phát và có chữ thay thế cho tín hiệu đúng/sai. Khi bật giảm chuyển động, thay toàn bộ cảnh bay/chìm/nhảy bằng trạng thái tĩnh và thông báo bằng chữ; không cần đợi hoạt cảnh.
8. Bố trí câu hỏi, các đáp án và nút đủ lớn trên điện thoại. Mỗi lựa chọn có nhãn rõ và bấm được bằng bàn phím, không bắt kéo hoặc bấm chính xác vào thuyền. Trình đọc màn hình đọc câu hỏi, thứ tự lựa chọn, trạng thái đang gửi và kết quả được phép hiển thị; không đọc đáp án ẩn hoặc thông tin từ ảnh trang trí.

## 9. Kiểm tra trước khi bàn giao bộ ảnh

- Tất cả ảnh khớp phong cách, tỷ lệ nhân vật, hướng sáng, viền và màu của ảnh tham chiếu. Không thay hình dạng chỉ huy hoặc thuyền giữa các frame.
- Kiểm tra nền trong suốt thật, không có ô caro được vẽ vào ảnh, không viền trắng, mép cắt hoặc lỗ ở khớp. Chồng thử từng phần lên ảnh mẫu để kiểm tra độ lệch.
- Kiểm tra mây che kín cả hai lá cờ trong trạng thái đầu; thuyền đúng và sai giống nhau trước khi mở mây. Không có chữ, số, điểm hay đáp án do Gemini sinh trong ảnh.
- Lắp thử các bộ phận chỉ huy: khớp vai, khuỷu, hông và đầu gối không hở; biểu cảm và mũ không nhảy vị trí khi thay frame; hoạt cảnh sai không gây sợ cho trẻ.
- Lắp thử hai kết quả và các tình huống mạng chậm, lưu lỗi, bấm liên tục; chỉ lộ kết quả khi hệ thống cho phép. Kiểm tra trường hợp 2 và 6 lựa chọn, màn hình nhỏ, bàn phím và giảm chuyển động.
- Giữ bản gốc, file tách lớp và tên file rõ ràng; ghi nhận file nào cần Gemini hoặc người thiết kế sửa lại. Không coi bộ ảnh đạt yêu cầu chỉ vì đã nhận đủ số tệp.
