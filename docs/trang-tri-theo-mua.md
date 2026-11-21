# Chủ đề theo mùa

Giáo viên chọn tại Cài đặt → Chủ đề website. Chế độ tự động bật chủ đề từ 7 ngày trước đến hết ngày lễ. Ngoài thời gian đó, website không trang trí. Có thể chọn cố định một chủ đề hoặc tắt trang trí.

Chạy `python manage.py migrate` khi triển khai thay đổi này để tạo bảng lưu lựa chọn. Ngày Tết và Trung thu tính theo lịch âm Việt Nam (UTC+7). Noel, 20/11 và Halloween tính theo ngày dương lịch.

Ảnh Noel được dùng từ `static/img/sunny-edu/noel Image/`. Ảnh 20/11 được dùng từ `static/img/sunny-edu/20-11/`; Halloween, Tết và Trung thu chưa có ảnh. Bổ sung tên ảnh vào `assets` trong `static/js/seasonal.js`. Trang quản lí giáo viên, trang làm bài và luyện nói không hiển thị trang trí.
