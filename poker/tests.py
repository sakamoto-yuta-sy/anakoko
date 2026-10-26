from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse


class UserManagementTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user("manager", password="old", is_staff=True)
        self.member = get_user_model().objects.create_user("member", password="old")

    def test_access_control(self):
        for name in ["user_create", "user_password_reset"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 302)
        self.client.force_login(self.member)
        self.assertNotContains(self.client.get(reverse("game_list")), reverse("user_create"))
        for name in ["user_create", "user_password_reset"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 403)
            self.assertEqual(self.client.post(reverse(name), {"username": "blocked", "user": self.admin.pk}).status_code, 403)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password("old"))
        self.assertFalse(get_user_model().objects.filter(username="blocked").exists())

    def test_create_user_and_reject_duplicate(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("game_list")), reverse("user_create"))
        response = self.client.post(reverse("user_create"), {"username": "new-user"})
        self.assertRedirects(response, reverse("user_create"))
        user = get_user_model().objects.get(username="new-user")
        self.assertTrue(user.check_password("new-user"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        response = self.client.post(reverse("user_create"), {"username": "new-user"})
        self.assertIn("username", response.context["form"].errors)

    def test_reset_requires_post_and_preserves_own_session(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("user_password_reset")).status_code, 200)
        self.member.refresh_from_db()
        self.assertTrue(self.member.check_password("old"))
        for user in [self.member, self.admin]:
            response = self.client.post(reverse("user_password_reset"), {"user": user.pk})
            self.assertRedirects(response, reverse("user_password_reset"))
            user.refresh_from_db()
            self.assertTrue(user.check_password(user.username))
        self.assertEqual(self.client.get(reverse("user_create")).status_code, 200)

    def test_csrf_required(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        for name in ["user_create", "user_password_reset"]:
            self.assertEqual(client.post(reverse(name), {}).status_code, 403)


class PasswordChangeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="password-test", password="original-password"
        )

    def test_login_required(self):
        response = self.client.get(reverse("password_change"))
        self.assertRedirects(response, "/login/?next=/password/change/")

    def test_password_change_and_session(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("game_list"))
        self.assertContains(response, reverse("password_change"))
        response = self.client.get(reverse("password_change"))
        self.assertContains(response, 'name="old_password"')
        response = self.client.post(reverse("password_change"), {
            "old_password": "original-password", "new_password1": "1", "new_password2": "1",
        })
        self.assertRedirects(response, reverse("password_change_done"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("1"))
        self.assertEqual(self.client.get(reverse("game_list")).status_code, 200)

    def test_invalid_passwords_leave_password_unchanged(self):
        self.client.force_login(self.user)
        for old, new, confirmation, field in [
            ("wrong", "1", "1", "old_password"),
            ("original-password", "1", "2", "new_password2"),
        ]:
            response = self.client.post(reverse("password_change"), {
                "old_password": old, "new_password1": new, "new_password2": confirmation,
            })
            self.assertEqual(response.status_code, 200)
            self.assertIn(field, response.context["form"].errors)
            self.user.refresh_from_db()
            self.assertTrue(self.user.check_password("original-password"))
