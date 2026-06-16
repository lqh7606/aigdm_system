import base64
import sys

from django.contrib.auth import authenticate, get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from accounts.models import UserProfile


class Command(BaseCommand):
    help = "Verify a system administrator account against the configured database."

    def add_arguments(self, parser):
        parser.add_argument("--username", help="系统管理员用户名。")
        parser.add_argument("--password-stdin", action="store_true", help="从标准输入读取本次密码。")
        parser.add_argument("--password-stdin-base64", action="store_true", help="从标准输入读取 UTF-8 base64 编码后的本次密码。")
        parser.add_argument("--expected-password-length", type=int, help="启动器本地密码框长度，用于诊断传输异常。")

    def handle(self, *args, **options):
        username = options.get("username") or ""
        if options["password_stdin_base64"]:
            password = self._read_base64_password()
        elif options["password_stdin"]:
            password = sys.stdin.read().rstrip("\r\n")
        else:
            password = ""
        if not username or not password:
            raise CommandError("系统管理员用户名或密码为空。")

        db_label = self._database_label()
        expected_length = options.get("expected_password_length")
        if expected_length is not None and expected_length != len(password):
            raise CommandError(
                f"系统管理员认证失败：启动器传入密码长度异常，本地长度 {expected_length}，服务端收到长度 {len(password)}。当前数据库：{db_label}"
            )
        user = get_user_model().objects.filter(username=username).first()
        if not user:
            raise CommandError(f"系统管理员认证失败：账号不存在（{username}）。当前数据库：{db_label}")
        if not user.is_active:
            raise CommandError(f"系统管理员认证失败：账号已停用（{username}）。当前数据库：{db_label}")
        auth_user = authenticate(username=username, password=password)
        if not auth_user:
            raise CommandError(f"系统管理员认证失败：密码不正确（{username}，收到密码长度 {len(password)}）。当前数据库：{db_label}")
        user = auth_user

        role = None
        try:
            role = user.userprofile.role
        except UserProfile.DoesNotExist:
            role = None

        if not (user.is_superuser or role == UserProfile.Role.ADMIN):
            raise CommandError(f"系统管理员认证失败：当前用户不是系统管理员（{username}）。当前数据库：{db_label}")

        self.stdout.write(self.style.SUCCESS("系统管理员认证通过。"))

    def _database_label(self):
        settings_dict = connection.settings_dict
        engine = settings_dict.get("ENGINE", "")
        name = settings_dict.get("NAME", "")
        host = settings_dict.get("HOST", "")
        port = settings_dict.get("PORT", "")
        if host or port:
            return f"{engine} / {name} / {host}:{port}"
        return f"{engine} / {name}"

    def _read_base64_password(self):
        payload = sys.stdin.read().strip().lstrip("\ufeff")
        try:
            return base64.b64decode(payload.encode("ascii"), validate=True).decode("utf-8")
        except Exception as exc:
            invalid_count = sum(1 for char in payload if char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
            raise CommandError(f"系统管理员认证失败：启动器密码传输格式无效（收到长度 {len(payload)}，非法字符数 {invalid_count}）。") from exc
