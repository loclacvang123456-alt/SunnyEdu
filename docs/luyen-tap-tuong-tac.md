# Luyện tập tương tác và hỗ trợ bài viết

## Cách giao bài

Khi tạo bài giao, giáo viên chọn “Luyện tập: từng câu một” hoặc “Kiểm tra: hiển thị các câu như bài thi”. Các bài cũ giữ cách hiển thị kiểm tra để không tự thay đổi bài đã giao. Bài luyện tập có nút câu trước/câu tiếp, câu trả lời vẫn được lưu như cũ; không tự công bố đáp án trước khi giáo viên cho phép.

## Kiểm tra bài viết tại máy

LanguageTool bản tự chạy có thể gợi ý lỗi chính tả và một số lỗi ngữ pháp, không đưa ra điểm tổng, không hiểu chắc ý học sinh và không thay giáo viên chấm bài. Website chỉ cho dùng ở câu viết trong bài luyện tập. Khi học sinh nhấn nút kiểm tra, văn bản được gửi tới LanguageTool trên cùng máy chủ; nếu chưa cấu hình hoặc dịch vụ ngừng hoạt động, nút sẽ báo chưa khả dụng, không tự gửi bài tới API công khai.

Đã thử local với LanguageTool 6.6, nguồn chính thức https://languagetool.org/download/LanguageTool-6.6.zip và Java 17. Bản tải khoảng 252 MB; thư mục `.runtime/` là dữ liệu cài đặt local, không đưa vào Git. Để mở lại dịch vụ sau khi khởi động lại máy, chạy trong PowerShell từ thư mục dự án:

```powershell
cd .runtime/languagetool/LanguageTool-6.6
java -cp languagetool-server.jar org.languagetool.server.HTTPServer --port 8081
```

Trong một cửa sổ PowerShell khác, từ thư mục dự án, bật kết nối local rồi chạy web:

```powershell
$env:LANGUAGETOOL_URL='http://127.0.0.1:8081/v2/check'
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001
```

Chỉ cấu hình địa chỉ localhost. LanguageTool server giữ trong mạng máy chủ, không mở ra Internet. Việc này chưa có nghĩa hệ thống đã sẵn sàng sản xuất: cần kiểm tra năng lực tải, giám sát và bảo vệ dữ liệu trước khi dùng cho học sinh thật.

Nguồn: [Hướng dẫn LanguageTool tự chạy](https://dev.languagetool.org/http-server), [điều kiện API công khai](https://dev.languagetool.org/public-http-api.html). Bản tự chạy không có các quy tắc AI của dịch vụ cloud.

## Phát âm

Azure Speech Pronunciation Assessment hỗ trợ đánh giá theo từ và âm vị IPA cho tiếng Anh Mỹ, từ lời nói so với câu mẫu. Không có ánh xạ một-một đáng tin cậy giữa mọi âm và chữ cái, vì vậy giao diện nên đánh dấu từ cần xem lại và hiển thị phần phiên âm tương ứng thay vì khẳng định từng chữ cái là một âm. Kết quả là gợi ý và có thể sai khi giọng nói nhỏ hoặc có tiếng ồn.

Theo bảng giá Microsoft được kiểm tra ngày 12/11/2026, gói F0 Speech-to-Text có 5 giờ âm thanh miễn phí mỗi tháng, dùng chung giữa các loại liên quan; hạn mức, khu vực và cách tính thực tế cần được kiểm tra trên tài khoản trước khi bật. Gói miễn phí có giới hạn đồng thời, không bảo đảm phục vụ 100 học sinh cùng nói. Không bật tính năng trả phí bổ sung khi chưa được chủ dự án chấp thuận.

Bản ghi âm phải gửi tới Microsoft để đánh giá; cần thông báo cho học sinh/phụ huynh, chọn vùng dịch vụ, quản lý khóa trên server và có sự đồng ý phù hợp trước khi bật. Không đặt khóa API trong trình duyệt hoặc commit vào dự án. Chưa có khóa Azure nên không thể kiểm chứng kết quả thực tế với dịch vụ này. Nguồn: [tài liệu phát âm](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-pronunciation-assessment), [giá Azure Speech](https://azure.microsoft.com/en-us/pricing/details/speech/), [hạn mức](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-services-quotas-and-limits), [quyền riêng tư dữ liệu](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/speech-service/speech-to-text/data-privacy-security).

## Game thuyền

Yêu cầu hình ảnh và prompt tạo các bộ phận riêng được ghi tại `game-tau-bien-asset.md`. Game chưa được coi là hoàn thành cho đến khi có bộ hình được duyệt và đã ghép, kiểm tra trên điện thoại. Không vẽ tạm đồ họa game bằng code. Trong bài kiểm tra, giữ giao diện nghiêm túc; không tiết lộ đáp án trước thời điểm được giáo viên cho phép.

Đường dẫn luyện nói thử là `/speaking/practice/` sau khi học sinh đăng nhập. Học sinh nhập từ hoặc câu mẫu rồi chọn ghi âm; hệ thống yêu cầu xác nhận cho từng bản ghi trước khi gửi đến Azure. Bản ghi không được dùng để tự đổi điểm bài tập. Khi chưa cấu hình, trang sẽ báo chưa khả dụng. Hệ thống hiện chưa có phần giáo viên giao sẵn câu mẫu cho mục luyện nói riêng.

Để người vận hành cấu hình sau khi đã kiểm tra chi phí và quyền xử lý dữ liệu, đặt `AZURE_SPEECH_KEY` và `AZURE_SPEECH_REGION` trong môi trường server. Không ghi khóa vào file dự án, trình duyệt hoặc chia sẻ trong chat. Dịch vụ giới hạn một yêu cầu đánh giá đồng thời; nếu bận, học sinh được yêu cầu thử lại. Kết nối Azure và kết quả IPA thật chưa được kiểm chứng vì chưa có tài khoản dịch vụ.

## Ba dạng câu hỏi đã thêm

Giáo viên có thể tạo câu sắp xếp từ thành câu, nối tranh với từ và chọn âm tiết mang trọng âm trong trình soạn đề. Học sinh có thể kéo hoặc bấm từng ô từ; với câu nối tranh có thể kéo từ tranh sang chữ, kéo ngược lại hoặc chọn lần lượt hai đầu. Câu trọng âm đổi màu khi chọn. Khi nộp, máy chủ chấm dựa trên đáp án giáo viên đã nhập. Mẫu nhập CSV/XLSX hiện chưa hỗ trợ ba loại này; cần tạo chúng trong trình soạn đề.

Các ảnh trong câu nối được giáo viên tải lên và phục vụ riêng cho học sinh có quyền làm bài. Ảnh đang lưu trên máy local; cần hoàn thiện sao lưu và lưu trữ chung trước khi dùng hệ thống thật trên nhiều máy chủ. Chưa có bộ hình game thuyền và chưa có màn game đó trong ứng dụng.
