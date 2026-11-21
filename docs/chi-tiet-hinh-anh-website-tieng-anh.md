# Tài liệu tạo hình ảnh cho website học tiếng Anh

Phiên bản: 12/11/2026. Mục đích: tạo bộ hình dùng cho trang chủ, trang nhập mã và các trạng thái trong website. Nội dung dưới đây là yêu cầu để gửi cho Gemini, chưa phải hình ảnh đã được tạo hoặc chức năng đã hoàn thành.

## 1. Định hướng chung

Website dành cho học sinh Việt Nam học và làm bài tiếng Anh, đồng thời cần tạo cảm giác rõ ràng và đáng tin cậy khi phụ huynh hoặc người lớn xem. Hướng hình ảnh được chọn là minh họa kỹ thuật số 2D hiện đại, gần với tranh minh họa biên tập cho website giáo dục. Các nhân vật có tỷ lệ cơ thể tự nhiên, gương mặt thân thiện, nét mặt vừa phải. Hình có chiều sâu nhờ các lớp trước và sau, màu chuyển nhẹ, nét viền mảnh và bóng đổ mềm. Tránh ảnh chụp, tranh 3D bóng nhựa, pixel art, phong cách truyện tranh quá trẻ con và các hiệu ứng phát sáng mạnh.

Bối cảnh chủ yếu là lớp học Việt Nam sáng sủa: bảng phấn xanh, bàn gỗ, sách bài tập, quyển vở, bút, hộp bút và tai nghe. Quần áo học sinh đơn giản, lịch sự, phù hợp độ tuổi, có thể dùng áo trắng và quần hoặc chân váy xanh đậm, không gắn phù hiệu hay tên trường có thật. Minh họa không cần mô phỏng người thật hay một học sinh cụ thể.

### Màu sắc

| Thành phần | Màu tham khảo | Cách dùng |
|---|---|---|
| Xanh dương chính | `#2563EB` | Áo khoác nhẹ, bìa sách, chi tiết nhấn. |
| Xanh lá bảng | `#3F786D` | Bảng phấn và một số vật dụng. |
| Xanh nhạt | `#DBEAFE` | Nền lớp học, mảng sáng. |
| Vàng nhạt | `#FDE68A` | Chi tiết nhỏ như bút chì, bìa vở, ánh nắng. |
| Kem sáng | `#FFFBF2` | Nền tường, vùng thoáng. |
| Màu chữ giao diện | `#0F172A` | Chỉ để người làm web tham khảo; không vẽ chữ này vào ảnh. |

Đây là màu định hướng, không yêu cầu mọi pixel khớp tuyệt đối. Màu tươi ở mức vừa phải, không dùng nền neon. Ánh sáng ban ngày đi từ phía trên bên trái, bóng mềm về phía dưới bên phải. Không làm mặt nhân vật bị cháy sáng hoặc vùng nền quá tối.

### Cách gửi cho Gemini

1. Tạo ảnh `01` trước. Chọn một phiên bản đạt yêu cầu về nét vẽ, nhân vật, màu và ánh sáng.
2. Khi tạo từng ảnh sau, đính kèm ảnh `01` làm hình tham chiếu và yêu cầu giữ cùng phong cách. Nếu công cụ không hỗ trợ ảnh tham chiếu, sao chép đoạn “Phong cách chung” bên dưới và dán trước prompt của từng ảnh.
3. Tạo từng ảnh thành một tệp riêng. Các ảnh 05A đến 05D phải được tạo riêng, không ghép thành một ảnh duy nhất. Mỗi prompt cần một lần tạo riêng để dễ sửa.
4. Tỷ lệ và kích thước bên dưới là mục tiêu xuất file. Nếu Gemini không cho chọn chính xác số pixel, chọn tỷ lệ gần nhất rồi xuất ở độ phân giải cao nhất có thể. Sau đó người làm web cắt hoặc chỉnh kích thước mà không kéo méo hình. Nếu Gemini không tạo được PNG trong suốt, dùng nền trắng hoặc kem phẳng, không có bóng nền, để xử lý sau.
5. Không đưa chữ, số, logo, watermark, nút bấm, thanh điều hướng, số liệu hoặc ảnh chụp giao diện vào hình. Chữ, icon điều hướng, nút và biểu đồ được dựng riêng trong website. Không yêu cầu Gemini thể hiện chữ tiếng Anh trên bảng hoặc bìa sách.

### Phong cách chung để dán vào Gemini

```text
Tạo một minh họa kỹ thuật số 2D hiện đại cho website học tiếng Anh của học sinh Việt Nam. Nét vẽ mềm, gọn, có chiều sâu nhẹ, giống tranh minh họa biên tập cho website giáo dục chuyên nghiệp. Nhân vật châu Á có tỷ lệ tự nhiên, gương mặt thân thiện, quần áo học sinh đơn giản và lịch sự. Không gian lớp học sáng sủa với bảng phấn xanh, bàn gỗ, sách, vở và bút. Dùng màu chủ đạo xanh dương #2563EB, xanh bảng #3F786D, xanh nhạt #DBEAFE, vàng nhạt #FDE68A và kem sáng #FFFBF2. Ánh sáng ban ngày dịu từ góc trên bên trái, bóng đổ mềm. Hình vui và gần gũi với trẻ em, bố cục gọn gàng để phụ huynh và giáo viên cũng thấy chuyên nghiệp. Không ảnh chụp, không 3D bóng nhựa, không chữ hoặc ký hiệu giống chữ, không số, không logo, không watermark, không nút bấm, không ảnh chụp màn hình, không thông tin cá nhân. Không thêm vật thể ngoài các vật được yêu cầu trong prompt tiếp theo.
```

Từ đây, tất cả vị trí phần trăm được tính trên khung hình từ trái sang phải và từ trên xuống dưới. Kích thước nhân vật là tỷ lệ ước lượng để Gemini hiểu bố cục, không phải yêu cầu đo pixel tuyệt đối.

## 2. Danh sách file

| Mã | Tên file đề xuất | Vị trí sử dụng | Tỷ lệ và kích thước mục tiêu | Ưu tiên |
|---|---|---|---|---|
| 01 | `home-hero-desktop.png` | Ảnh chính trên đầu trang chủ | 16:9, 1920 × 1080 px | Cần trước |
| 02 | `home-four-skills.png` | Banner phụ hoặc phần giới thiệu bốn kỹ năng | 16:9, 1920 × 1080 px | Sau |
| 03 | `home-how-it-works.png` | Phần hướng dẫn vào học bằng mã | 4:3, 1200 × 900 px | Sau |
| 04 | `home-teacher-feedback.png` | Phần giới thiệu việc giáo viên theo dõi và chấm bài | 4:3, 1200 × 900 px | Sau |
| 05A | `skill-listening.png` | Thẻ kỹ năng listening | 1:1, 768 × 768 px | Cần trước |
| 05B | `skill-speaking.png` | Thẻ kỹ năng speaking | 1:1, 768 × 768 px | Cần trước |
| 05C | `skill-reading.png` | Thẻ kỹ năng reading | 1:1, 768 × 768 px | Cần trước |
| 05D | `skill-writing.png` | Thẻ kỹ năng writing | 1:1, 768 × 768 px | Cần trước |
| 06 | `student-login.png` | Trang nhập mã học sinh | 4:3, 1200 × 900 px | Cần trước |
| 07 | `empty-assignments.png` | Trạng thái chưa có bài tập | 1:1, 512 × 512 px | Cần trước |
| 08 | `submission-success.png` | Xác nhận nộp bài thành công | 1:1, 512 × 512 px | Cần trước |
| 09 | `home-background.png` | Nền trang trí nhẹ cho một phần trang chủ | 16:9, 1920 × 1080 px | Tùy chọn |

Tổng cộng 12 tệp. PNG là định dạng trung gian để xem và chỉnh; khi đưa lên web, người làm web có thể xuất WebP hoặc AVIF nếu hình vẫn rõ. Không dùng file nền trong suốt nếu công cụ tạo nền giả dạng ô caro.

## 3. Chi tiết từng ảnh

### 01. Ảnh chính đầu trang chủ

**Mục đích:** tạo cảm giác đây là lớp học tiếng Anh thân thiện, có tương tác giữa học sinh và giáo viên. Ảnh đặt ở phần đầu trang chủ cùng tiêu đề và nút “Vào học” do website dựng riêng.

**Bố cục và số lượng:** ảnh ngang 16:9. Vùng 0–40% bên trái để trống, chỉ có nền tường kem rất nhạt. Nhân vật nằm trong vùng 45–93% chiều ngang. Có đúng ba học sinh và một giáo viên. Một bàn học dài ở vùng dưới bên phải; một bảng phấn xanh phía sau, không chữ. Có ba quyển sách, hai quyển vở, ba cây bút và một tai nghe, tất cả được sắp tự nhiên trên bàn hoặc đang được dùng. Không thêm cặp sách, cây cối hoặc các vật trang trí khác.

**Vị trí:** học sinh thứ nhất ngồi ở khoảng 56% chiều ngang và đang đọc một quyển sách; học sinh thứ hai ngồi ở khoảng 70% và đang viết trong vở; học sinh thứ ba ở khoảng 83%, đeo tai nghe quanh tai và nhìn về quyển sách trên bàn. Giáo viên đứng phía sau giữa học sinh thứ hai và thứ ba, cúi nhẹ để hướng dẫn. Chừa ít nhất 5% lề ngoài cùng bên phải; không cắt đầu hoặc tay nhân vật. Nhóm người chiếm khoảng 65% chiều cao khung hình, từ y=25% đến y=90%.

**Ánh sáng:** ánh sáng ban ngày dịu từ cửa sổ ngoài khung hình bên trái, bóng nhẹ phía dưới bàn. Nền sạch, đủ tương phản để các nhân vật tách khỏi nền.

**Prompt:**

```text
Tạo ảnh hero ngang 16:9, mục tiêu 1920 × 1080 px, theo phong cách chung và ảnh tham chiếu đã gửi. Đây là hình đầu trang cho website học tiếng Anh. Để 40% chiều ngang bên trái gần như trống, chỉ có tường màu kem rất nhạt, để website đặt chữ riêng. Trong vùng bên phải có đúng ba học sinh châu Á và một giáo viên trong lớp học sáng sủa. Học sinh thứ nhất ngồi đọc sách ở gần giữa ảnh, học sinh thứ hai ngồi viết vở ở bên phải học sinh thứ nhất, học sinh thứ ba đeo tai nghe ở phía phải. Giáo viên đứng phía sau, cúi nhẹ quan sát và hướng dẫn. Có một bàn gỗ dài, ba quyển sách, hai quyển vở, ba cây bút và một tai nghe; một bảng phấn xanh trống ở phía sau. Không thêm vật dụng khác. Cả nhóm người nằm trong 65% chiều cao ở phía phải, không cắt đầu, tay hoặc bàn học. Ánh sáng ban ngày mềm từ bên trái, bóng đổ dịu. Không chữ, số, logo, watermark, nút bấm hoặc giao diện website.
```

**Kiểm tra trước khi nhận:** có đủ 4 người, không ai bị dính tay hoặc mặt vào vật khác; vùng bên trái đủ thoáng; bảng và sách không xuất hiện chữ giả. Trên điện thoại nên đặt ảnh dưới phần chữ hoặc tạo bản cắt riêng, không cắt lấy giữa ảnh rồi làm mất nhóm người.

### 02. Banner bốn hoạt động học

**Mục đích:** giới thiệu bốn kỹ năng trên trang chủ. Đây là ảnh dự kiến cho nội dung thứ hai của slider trên trang chủ; cần nối ảnh đổi theo nội dung slide.

**Bố cục và số lượng:** ảnh ngang 16:9, vùng trái 0–32% để thoáng. Bên phải có đúng bốn học sinh trong cùng một phòng học. Có một bàn gỗ dài, hai quyển sách, một quyển vở, một cây bút, một tai nghe và một micro để bàn. Bảng phấn chỉ là nền, không viết chữ. Không phân chia thành bốn ô có đường kẻ.

**Vị trí:** trong vùng 35–95% chiều ngang, từ trái sang phải lần lượt là học sinh đeo tai nghe, học sinh nói trước micro, học sinh đọc sách và học sinh viết vở. Bốn em tạo thành một hàng cong nhẹ, không che mặt nhau. Chừa lề 5% xung quanh nhóm.

**Prompt:**

```text
Tạo banner ngang 16:9, mục tiêu 1920 × 1080 px, theo ảnh tham chiếu và phong cách chung. Để bên trái khoảng một phần ba ảnh là nền sáng thoáng để đặt chữ sau. Bên phải có đúng bốn học sinh châu Á trong một lớp học, sắp theo chiều từ trái sang phải: một em đeo tai nghe, một em nói trước micro để bàn, một em đọc sách và một em viết vở. Dùng một bàn gỗ dài, hai sách, một vở, một bút, một tai nghe và một micro; phía sau là một bảng phấn xanh trống. Các hoạt động cùng nằm trong một cảnh thống nhất, không chia ảnh thành bốn ô. Không che mặt, không cắt người ở rìa ảnh. Ánh sáng ban ngày dịu từ trên bên trái. Không chữ, số, logo, watermark hoặc giao diện website.
```

### 03. Hướng dẫn vào học bằng mã

**Mục đích:** đặt cạnh phần giải thích học sinh nhận mã, nhập mã rồi làm bài. Không thể hiện mã thật trong hình.

**Bố cục và số lượng:** ảnh 4:3. Đúng một học sinh, một giáo viên, một bàn gỗ, một máy tính xách tay, một thẻ mã trống, một quyển sách, một quyển vở và một cây bút. Không có học sinh hoặc thiết bị khác.

**Vị trí:** học sinh ngồi ở vùng giữa phải, chiếm khoảng 55% chiều cao; máy tính ở giữa phía dưới, màn hình quay chếch về học sinh. Giáo viên đứng bên trái phía sau, chỉ tay vào thẻ trống đặt cạnh máy tính. Thẻ có dạng hình chữ nhật đơn sắc, không có ký tự. Vùng trên bên trái còn khoảng 20% diện tích thoáng.

**Prompt:**

```text
Tạo minh họa 4:3, mục tiêu 1200 × 900 px, cho phần hướng dẫn vào học bằng mã. Có đúng một học sinh châu Á ngồi ở giữa bên phải và một giáo viên đứng phía sau bên trái, hướng dẫn nhẹ nhàng. Trên một bàn gỗ có một máy tính xách tay, một thẻ hình chữ nhật hoàn toàn trống, một quyển sách, một quyển vở và một cây bút. Giáo viên chỉ vào thẻ, học sinh nhìn về máy tính với vẻ tập trung. Màn hình máy tính chỉ có một mặt phẳng màu nhạt, không vẽ trang web hoặc ký hiệu. Chừa khoảng thoáng ở góc trên trái. Giữ cùng nét vẽ, màu và ánh sáng của ảnh tham chiếu. Không thêm người hay vật khác, không chữ, số, logo, watermark hoặc thông tin cá nhân.
```

### 04. Giáo viên theo dõi và nhận xét

**Mục đích:** giải thích cho người lớn rằng giáo viên xem bài, chấm tự luận và theo dõi tiến bộ. Không tạo biểu đồ hoặc điểm số giả.

**Bố cục và số lượng:** ảnh 4:3, đúng một giáo viên và một học sinh ngồi cạnh nhau, một bàn, một quyển vở mở, một cây bút đỏ, một quyển sách đóng và một máy tính xách tay. Bảng phấn xanh trống ở xa phía sau.

**Vị trí:** giáo viên ở 35% chiều ngang, học sinh ở 65%, hai người hướng về quyển vở đặt giữa bàn. Quyển vở chiếm khoảng 20% chiều ngang khung hình. Máy tính ở góc dưới phải, màn hình nhìn nghiêng và để trống. Nét mặt quan tâm, bình tĩnh, không chỉ tay trách mắng.

**Prompt:**

```text
Tạo minh họa 4:3, mục tiêu 1200 × 900 px, về giáo viên theo dõi bài học của học sinh. Trong lớp học sáng có đúng một giáo viên ở bên trái và một học sinh châu Á ở bên phải, cùng nhìn vào một quyển vở mở đặt giữa bàn. Giáo viên cầm một bút đỏ để nhận xét, học sinh lắng nghe với nét mặt thoải mái. Trên bàn chỉ có một quyển sách đóng và một máy tính xách tay đặt góc phải; màn hình máy tính là một mặt sáng trống. Phía sau có một bảng phấn xanh trống. Bố cục cân bằng, tay và mặt không bị che, ánh sáng nhẹ từ trên trái. Giữ phong cách và màu theo ảnh tham chiếu. Không chữ, điểm số, biểu đồ, logo hoặc watermark.
```

### 05A–05D. Bộ bốn thẻ kỹ năng

**Quy chuẩn chung:** tạo bốn tệp riêng theo tỷ lệ 1:1, mục tiêu 768 × 768 px/tệp. Mỗi ảnh có đúng một học sinh ngồi sau một bàn gỗ, nhìn nghiêng ba phần tư, nửa thân trên. Đầu học sinh nằm khoảng y=15–38%, bàn ở y=68–90%, chừa 10% lề bốn phía. Nền kem sáng với một vòng tròn xanh nhạt phía sau nhân vật, không có khung viền. Dùng cùng một nét vẽ, ánh sáng và tỷ lệ nhân vật trong cả bốn ảnh; có thể khác nhân vật, không yêu cầu bốn ảnh khớp khuôn mặt. Mỗi ảnh tập trung vào một hành động. Không để nhân vật hoặc vật bị cắt mất khi ảnh thu nhỏ.

**05A: Listening.** Một học sinh ở giữa đeo một tai nghe, trước mặt là một quyển sách đóng. Hai tay đặt trên bàn, không có micro hoặc bút. Không thêm nốt nhạc vì đây là bài nghe tiếng Anh.

```text
Tạo một ảnh vuông 1:1, mục tiêu 768 × 768 px, cho thẻ listening. Có đúng một học sinh châu Á nhìn nghiêng ba phần tư, nửa thân trên, ngồi giữa sau một bàn gỗ và đeo một tai nghe. Có một quyển sách đóng đặt phía trước; hai tay đặt tự nhiên trên bàn. Không micro, không bút, không nốt nhạc, không vật khác. Nền kem sáng với một vòng tròn xanh nhạt sau nhân vật; đầu ở phần trên giữa, bàn ở phần dưới, chừa 10% lề quanh ảnh. Cùng nét vẽ, màu và ánh sáng của ảnh tham chiếu. Không chữ, số, logo hay watermark.
```

**05B: Speaking.** Một học sinh ở giữa nói hướng về một micro để bàn đặt bên phải ảnh. Có một quyển vở đóng bên trái ảnh, không tai nghe. Miệng mở nhẹ như đang nói, không hét.

```text
Tạo một ảnh vuông 1:1, mục tiêu 768 × 768 px, cho thẻ speaking. Có đúng một học sinh châu Á nhìn nghiêng ba phần tư, nửa thân trên, ngồi giữa sau một bàn gỗ và đang nói nhẹ trước một micro để bàn đặt phía phải ảnh. Một quyển vở đóng đặt phía trái. Không tai nghe, không vật khác. Nền kem sáng với một vòng tròn xanh nhạt sau nhân vật; chừa 10% lề quanh ảnh. Dùng cùng bố cục, nét vẽ, màu và ánh sáng của ảnh listening và ảnh tham chiếu. Không chữ, số, logo hay watermark.
```

**05C: Reading.** Một học sinh ở giữa cầm một quyển sách mở bằng hai tay; sách phía trước ngực và không che mặt. Không tai nghe, micro hay bút.

```text
Tạo một ảnh vuông 1:1, mục tiêu 768 × 768 px, cho thẻ reading. Có đúng một học sinh châu Á nhìn nghiêng ba phần tư, nửa thân trên, ngồi giữa sau một bàn gỗ. Học sinh cầm một quyển sách mở bằng hai tay và nhìn vào sách; sách ở dưới mặt, không che mắt hoặc miệng. Không tai nghe, micro, bút hay vật khác. Nền kem sáng với một vòng tròn xanh nhạt sau nhân vật; chừa 10% lề quanh ảnh. Dùng cùng bố cục, nét vẽ, màu và ánh sáng của bộ thẻ kỹ năng. Không chữ trên sách, không số, logo hay watermark.
```

**05D: Writing.** Một học sinh ở giữa viết bằng một cây bút trên một quyển vở mở. Một tay cầm bút, một tay giữ vở, không tai nghe hay micro.

```text
Tạo một ảnh vuông 1:1, mục tiêu 768 × 768 px, cho thẻ writing. Có đúng một học sinh châu Á nhìn nghiêng ba phần tư, nửa thân trên, ngồi giữa sau một bàn gỗ. Một tay cầm một cây bút đang viết vào một quyển vở mở trên bàn, tay kia giữ nhẹ quyển vở. Không tai nghe, micro, sách hay vật khác. Nền kem sáng với một vòng tròn xanh nhạt sau nhân vật; chừa 10% lề quanh ảnh. Dùng cùng bố cục, nét vẽ, màu và ánh sáng của bộ thẻ kỹ năng. Trang vở để trống, không chữ, số, logo hay watermark.
```

### 06. Trang nhập mã

**Mục đích:** hình cạnh form nhập mã. Ảnh chỉ minh họa, không chứa mã có thể dùng đăng nhập.

**Bố cục và số lượng:** ảnh 4:3. Một học sinh đứng hơi lệch phải, một thẻ hình chữ nhật trống, một cặp sách đặt dưới chân và hai quyển sách xếp cạnh cặp. Không có form hay máy tính trong hình.

**Vị trí:** học sinh chiếm khoảng 60% chiều cao và ở vùng 45–80% chiều ngang. Thẻ trống ở trước ngực, được giữ bằng hai tay, không che mặt. Cặp và sách nằm ở góc dưới phải. Vùng bên trái để nền kem nhạt, không đồ vật.

**Prompt:**

```text
Tạo minh họa 4:3, mục tiêu 1200 × 900 px, cho trang nhập mã học tiếng Anh. Có đúng một học sinh châu Á đứng lệch sang phải, gương mặt thân thiện, cầm một thẻ hình chữ nhật màu kem hoàn toàn trống bằng hai tay trước ngực. Thẻ không che mặt và không có mã. Một chiếc cặp sách cùng hai quyển sách xếp ở dưới chân phía phải. Không thêm người, máy tính, ô nhập hay nút bấm. Nửa bên trái để nền sáng thoáng. Nhân vật không bị cắt đầu hoặc chân, ánh sáng dịu từ trên trái, cùng nét vẽ và màu của ảnh tham chiếu. Không chữ, số, logo hay watermark.
```

### 07. Chưa có bài tập

**Mục đích:** minh họa nhỏ cạnh dòng thông báo chưa có bài. Hình không được khiến học sinh nghĩ rằng đã hoàn thành một bài cụ thể.

**Bố cục và số lượng:** ảnh vuông, một quyển vở mở ở giữa, hai quyển sách đóng xếp chồng ở bên trái, một bút chì nằm chéo bên phải. Có đúng hai ngôi sao nhỏ trên cao làm trang trí. Không có người, dấu tích hay huy chương.

**Kích thước:** toàn bộ cụm vật thể nằm trong vùng giữa 70% khung hình, chừa 15% lề mỗi phía. Nền trong suốt thật nếu công cụ hỗ trợ, nếu không dùng nền kem phẳng.

**Prompt:**

```text
Tạo minh họa vuông 1:1, mục tiêu 512 × 512 px, cho trạng thái chưa có bài tập. Ở giữa là một quyển vở mở hoàn toàn trống; bên trái có hai quyển sách đóng xếp chồng; bên phải có một bút chì nằm chéo. Phía trên có đúng hai ngôi sao nhỏ làm trang trí. Không có người, dấu tích, huy chương hoặc đồ vật khác. Cả nhóm nằm trong 70% diện tích chính giữa, chừa khoảng trống xung quanh. Nét vẽ 2D mềm, màu đồng nhất với ảnh tham chiếu, ánh sáng nhẹ từ trên trái. Nền trong suốt nếu hỗ trợ, nếu không thì nền kem phẳng. Không chữ, số, logo hay watermark.
```

### 08. Đã nộp bài

**Mục đích:** động viên sau khi máy chủ xác nhận nộp thành công. Hình không biểu thị điểm, phần thưởng hoặc thứ hạng.

**Bố cục và số lượng:** một quyển vở đóng ở giữa, một cây bút đặt chéo phía trước, một dấu tích trang trí dạng hình khối phía trên bên phải. Đúng ba ngôi sao nhỏ, không pháo hoa, cúp hay huy chương.

**Kích thước:** cụm đồ vật nằm trong 70% vùng giữa ảnh vuông, chừa 15% lề. Nền trong suốt thật nếu có thể, nếu không dùng nền kem phẳng.

**Prompt:**

```text
Tạo minh họa vuông 1:1, mục tiêu 512 × 512 px, cho màn hình xác nhận đã nộp bài. Ở giữa có một quyển vở đóng; một cây bút đặt chéo phía trước quyển vở; một dấu tích lớn dạng hình khối màu xanh lá nằm phía trên bên phải. Có đúng ba ngôi sao nhỏ phân bố quanh cụm vật thể. Không có người, điểm số, cúp, huy chương, pháo hoa hay đồ vật khác. Cụm hình nằm trong 70% vùng giữa ảnh, chừa lề thoáng. Phong cách và ánh sáng giống bộ ảnh tham chiếu. Nền trong suốt nếu hỗ trợ, nếu không nền kem phẳng. Không chữ, số, logo hay watermark.
```

### 09. Nền trang trí nhẹ

**Mục đích:** dùng sau các khối giới thiệu, không dùng sau câu hỏi, đoạn đọc hoặc form. Có thể bỏ ảnh này nếu nền trơn giúp đọc tốt hơn.

**Bố cục và số lượng:** ảnh 16:9. Nền kem sáng gần như phẳng, có 6 họa tiết: hai quyển sách nhỏ, hai cây bút chì và hai hình ngôi sao. Chỉ đặt ở 15% sát cạnh trái và 15% sát cạnh phải. Giữa ảnh giữ trống 70% chiều ngang. Các họa tiết là hình phẳng xanh nhạt hoặc vàng nhạt, không đổ bóng đậm, tổng diện tích dưới 10% bề mặt.

**Prompt:**

```text
Tạo ảnh nền ngang 16:9, mục tiêu 1920 × 1080 px, cho một phần trang chủ giáo dục. Nền kem rất sáng và gần như phẳng. Chỉ có sáu họa tiết nhỏ dạng hình phẳng: hai quyển sách, hai cây bút chì và hai ngôi sao. Đặt ba họa tiết ở dải 15% sát cạnh trái và ba họa tiết ở dải 15% sát cạnh phải; để trống 70% chiều ngang ở giữa. Các họa tiết có màu xanh nhạt hoặc vàng nhạt, độ tương phản thấp, không bóng đậm, tổng diện tích nhỏ hơn một phần mười ảnh. Không có nhân vật, bảng đen lớn, chữ, số, logo, watermark hoặc giao diện. Màu sắc phải khớp bộ ảnh tham chiếu.
```

## 4. Dùng ảnh trên website

Trang chủ dự kiến theo thứ tự: thanh điều hướng; ảnh 01 và phần giới thiệu; bốn thẻ 05A–05D; phần giới thiệu cách vào học với ảnh 03; phần dành cho phụ huynh và giáo viên với ảnh 04; thông tin liên hệ do chủ website cung cấp. Ảnh 02 dự kiến dùng cho nội dung thứ hai của slider trên trang chủ. Slider có nút chuyển và hỗ trợ bàn phím; nếu bổ sung chế độ tự chạy thì phải có nút tạm dừng. Ảnh 06 dùng trên trang nhập mã, ảnh 07 và 08 dùng trong khu vực học sinh sau khi đăng nhập.

Khi dựng desktop, ảnh 01 đặt cạnh hoặc làm nền cho phần giới thiệu với chữ do web tạo. Khi dựng mobile, đặt chữ và nút lên trước, ảnh xuống dưới và giữ trọn nhân vật. Nếu cần một ảnh dọc riêng, yêu cầu Gemini dựng lại từ ảnh 01 theo tỷ lệ 4:5, nhân vật nằm trong 80% vùng giữa, không cắt người; không tự kéo ảnh ngang thành ảnh dọc. Không đặt chữ quan trọng, nút điều hướng hay đáp án vào trong các file ảnh. Hình trang trí dùng alt rỗng; hình mang nội dung cần mô tả ngắn trong alt khi lập trình.

## 5. Kiểm tra trước khi gửi ảnh cho người làm web

- Xem ảnh ở kích thước lớn và trên điện thoại: mặt, bàn tay và đồ vật có đầy đủ, không méo hoặc dính vào nhau.
- Kiểm tra có đúng số người và các vật chính trong prompt; nếu Gemini không đáp ứng chính xác, yêu cầu sửa ảnh đó, không cần tạo lại cả bộ.
- Kiểm tra sách, bảng và màn hình không có chữ hoặc ký hiệu giả, đặc biệt ở các góc nhỏ.
- Xem bốn thẻ kỹ năng cạnh nhau để kiểm tra kích thước nhân vật, nét vẽ, màu, ánh sáng và khoảng trống có đồng đều.
- Kiểm tra vùng trống và cách cắt ở desktop/mobile. Nếu nền làm chữ khó đọc, dùng nền trơn hoặc để chữ bên ngoài ảnh.
- Lưu từng file riêng với tên đề xuất; giữ cả bản gốc và bản đã tối ưu. Không coi hình sinh bằng AI là ảnh học sinh hoặc lớp học thật.

## 6. Bổ sung logo Sunny Edu

Tên website là **Sunny Edu**. Logo là mặt trời tạo bằng chữ, ưu tiên bản vector nền trong suốt để đặt trên thanh điều hướng và dùng được ở kích thước nhỏ.

- Phần tròn ở giữa được tạo từ chính dòng chữ **SUNNY EDU**, viết hoa, uốn cong theo đường tròn và trải đều hết vòng. Chữ dày, nét đậm, chắc và khoảng cách vừa đủ để tạo cảm giác vòng tròn đầy đặn; không dùng chữ mảnh khiến hình tròn bị loãng.
- Có **sáu tia nắng** xếp đều quanh vòng tròn. Mỗi tia là một chữ cái viết hoa A, B hoặc C, được kéo hẹp theo bề ngang và cao theo hướng từ tâm ra ngoài để giống tia nắng. Thứ tự theo chiều kim đồng hồ từ tia trên cùng: A, B, C, A, B, C.
- Chừa một khoảng rõ giữa các tia và vòng chữ, giữ các chữ không chạm hoặc chồng lên nhau. Tránh thêm vòng tròn vẽ sẵn, khuôn mặt, mắt, miệng, hình người hoặc vật trang trí khác.
- Màu đề xuất: chữ vòng màu xanh dương đậm; sáu tia màu vàng nắng. Nền trong suốt hoặc nền trắng phẳng nếu công cụ không hỗ trợ trong suốt. Kiểm tra khả năng đọc trên cả nền sáng và khi thu nhỏ.

Prompt để thử thiết kế với Gemini:

```text
Thiết kế một logo vector phẳng cho website giáo dục tên SUNNY EDU, khung hình vuông, nhìn chính diện, nền trong suốt nếu hỗ trợ. Hình chính là mặt trời tạo hoàn toàn bằng chữ. Ở giữa, viết đúng duy nhất dòng chữ SUNNY EDU bằng chữ in hoa và uốn các chữ theo một đường tròn khép kín, phân bố các ký tự quanh vòng tròn; dùng chữ sans serif rất dày và chắc để vòng tròn không bị loãng, các ký tự rõ ràng không dính nhau. Bên ngoài vòng chữ có đúng sáu tia nắng đặt đều nhau mỗi 60 độ. Mỗi tia là một chữ cái in hoa A, B hoặc C kéo hẹp theo chiều ngang, cao theo hướng xuyên tâm để trông như một tia nắng. Từ tia trên cùng theo chiều kim đồng hồ dùng thứ tự A, B, C, A, B, C. Vòng chữ màu xanh dương đậm, sáu tia màu vàng nắng. Giữ khoảng cách giữa vòng chữ và tia, không có nét viền tròn riêng, không hình tròn đặc, không mặt trời có mắt miệng, không gradient, không bóng, không biểu tượng hay chữ khác, không watermark. Logo phải cân đối và có khoảng trống xung quanh để không cắt mất tia.
```

Kiểm tra chữ trong ảnh tạo bằng AI vì công cụ có thể viết sai hoặc sai số tia. Nếu chữ hoặc vị trí chưa đúng, tiếp tục yêu cầu Gemini điều chỉnh hoặc nhờ nhà thiết kế hoàn thiện trước khi chốt logo chính thức.

## 7. Vị trí chính xác để gắn ảnh vào website

Các ảnh dưới đây đang chờ được tạo và gửi vào dự án. Không tự đổi tên hoặc giả định ảnh đã tồn tại. Sau khi tạo, đặt các tệp vào `static/img/sunny-edu/` theo tên trong bảng. Nếu ảnh Gemini trả về định dạng khác, giữ bản gốc và tạo một bản web cùng tên tương ứng; khi lập trình, dùng đúng đuôi tệp thực tế. Các vị trí “cần bổ sung” hiện chưa có thành phần tương ứng trên giao diện.

| Ảnh | Trang và vị trí cụ thể | Cách đặt trên máy tính và điện thoại | Trạng thái |
|---|---|---|---|
| `home-hero-desktop.png` | Trang chủ `/`, khối banner đầu trang, vùng minh họa bên phải của tiêu đề “Học tiếng Anh vui mỗi ngày” và nút “Vào học ngay”. Trong `templates/landing.html`, thay hình minh họa hiện tại trong `.hero-art` khi đã có ảnh. | Desktop: chữ và nút bên trái, ảnh bên phải; mobile: chữ và nút trước, ảnh xếp bên dưới. Giữ đủ đầu, tay và bàn học. | Có vùng đặt ảnh, ảnh đang chờ tạo. |
| `home-four-skills.png` | Trang chủ `/`, khối banner đầu trang khi chọn nội dung slider số 2. Hiện slider chỉ đổi chữ, nên cần bổ sung liên kết ảnh với từng slide; không tự gắn ảnh nếu chưa hoàn tất thay đổi này. | Bố cục giống ảnh 01; ảnh phải đổi cùng slide và không che phần chữ, nút hoặc điều khiển. Trên mobile xếp ảnh dưới chữ. | Cần nối ảnh theo từng slide; ảnh đang chờ tạo. |
| `home-how-it-works.png` | Trang chủ `/`, khu vực `#cach-hoc`, cạnh khối “Ba bước nhỏ, một hành trình vui”. Phần ba bước vẫn phải hiển thị rõ; cần mở rộng bố cục hiện có để dành chỗ cho ảnh. | Desktop: ảnh cạnh nội dung hướng dẫn, không đè lên ba bước; mobile: tiêu đề và mô tả trước, ảnh sau đó, rồi đến ba bước. | Cần bổ sung chỗ đặt ảnh; ảnh đang chờ tạo. |
| `home-teacher-feedback.png` | Trang chủ `/`, một phần mới “Giáo viên đồng hành” đặt sau phần `#cach-hoc` và trước khối “Một ngày mới, một điều mới để học”. Nội dung chỉ mô tả chức năng đã được xác nhận hoạt động. | Desktop: ảnh bên trái, đoạn giới thiệu bên phải; mobile: tiêu đề, ảnh, đoạn giới thiệu xếp dọc. | Phần này chưa có, cần bổ sung; ảnh đang chờ tạo. |
| `skill-listening.png` | Trang chủ `/`, phần `#ky-nang`, thẻ “Lắng nghe”, thay hình ký hiệu trong `.skill-listen .skill-icon`. | Ảnh nằm phía trên tên kỹ năng; giữ cùng kích thước và tỷ lệ với ba ảnh kỹ năng khác. Mobile dùng lưới hai cột nếu còn đủ rộng, không cắt nhân vật. | Có thẻ và chỗ minh họa; ảnh đang chờ tạo. |
| `skill-speaking.png` | Trang chủ `/`, phần `#ky-nang`, thẻ “Tập nói”, thay `.skill-speak .skill-icon`. | Cùng vị trí và kích thước với ảnh listening. Không dùng ảnh làm nút bấm. | Có thẻ và chỗ minh họa; ảnh đang chờ tạo. |
| `skill-reading.png` | Trang chủ `/`, phần `#ky-nang`, thẻ “Đọc hiểu”, thay `.skill-read .skill-icon`. | Cùng vị trí và kích thước với ảnh listening. Sách không được che phần chữ của thẻ. | Có thẻ và chỗ minh họa; ảnh đang chờ tạo. |
| `skill-writing.png` | Trang chủ `/`, phần `#ky-nang`, thẻ “Tập viết”, thay `.skill-write .skill-icon`. | Cùng vị trí và kích thước với ảnh listening. Chữ mô tả nằm ngoài ảnh. | Có thẻ và chỗ minh họa; ảnh đang chờ tạo. |
| `student-login.png` | Trang nhập mã `/login/`, trong `.login-intro .illustration` của `templates/accounts/student_login.html`, thay hình cuốn sách hiện tại. Không nằm trong ô nhập mã. | Desktop: hình cạnh form; mobile: hình không được đẩy form quá xa, có thể thu nhỏ hoặc ẩn theo bố cục thực tế. | Có vùng đặt ảnh; ảnh đang chờ tạo. |
| `empty-assignments.png` | Trang “Bài của em” `/student/`, chỉ trong `.empty-state` của `templates/student/dashboard.html` khi không có bài được giao, thay dấu minh họa hiện tại. | Đặt phía trên dòng “Chưa có bài tập”, giới hạn khoảng 160 × 160 CSS px; ảnh nhỏ hơn trên màn hình hẹp. | Có trạng thái trống; ảnh đang chờ tạo. |
| `submission-success.png` | Trang làm bài `/student/assignments/<mã-bài>/`, chỉ hiện tại khu vực xác nhận sau khi máy chủ trả `submitted_at`. Hiện `static/js/attempt.js` mới hiển thị thông báo chữ, nên cần bổ sung vùng xác nhận để đặt ảnh. | Hiện cùng dòng “Đã nộp lúc ...”, giới hạn khoảng 160 × 160 CSS px. Không hiện khi đang gửi, lỗi hoặc chỉ lưu nháp. | Cần bổ sung vùng xác nhận; ảnh đang chờ tạo. |
| `home-background.png` | Trang chủ `/`, chỉ làm nền trang trí nhạt phía sau một phần giới thiệu, ví dụ `.intro-section`. Không đặt sau câu hỏi, form nhập mã hoặc bảng điểm. | Nền trải theo chiều rộng vùng, giữ chữ dễ đọc; trên mobile kiểm tra cắt ảnh hoặc thay bằng nền màu trơn. | Tùy chọn, cần kiểm tra tương phản; ảnh đang chờ tạo. |

Logo là một tệp riêng sẽ do Gemini tạo theo mục 6. Sau khi bạn chọn logo, người làm web gắn cùng một file vào thanh đầu trang và chân trang chủ, trang `/login/`, thanh điều hướng học sinh và phần giáo viên. Hiện giao diện dùng chữ “Sunny Edu” để chờ logo; không dùng mẫu logo do agent tự vẽ.

Khi gắn ảnh, cập nhật template hoặc CSS tương ứng, dùng đường dẫn static của Django và khai báo `width`/`height` theo tỷ lệ ảnh để giảm xê dịch khi tải trang. Ảnh chỉ trang trí có `alt=""`; ảnh mang thông tin cần alt ngắn, đúng nội dung. Kiểm tra lại trang ở desktop, mobile và khi ảnh tải lỗi. Không đặt thông tin quan trọng duy nhất trong ảnh.
