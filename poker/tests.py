from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import Game, Order, Rebuy, Result


class RebuySettlementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("player", password="1")
        self.other = get_user_model().objects.create_user("other", password="1")
        self.game = Game.objects.create(name="新方式", date="2026-10-26", table_fee=2000,
                                        initial_chips=1000, rebuy_chips=1000, created_by=self.user)
        self.game.participants.add(self.user, self.other)
        Order.objects.create(game=self.game, user=self.user, name="飲食", price=500)
        Rebuy.objects.create(game=self.game, user=self.user, count=3)
        self.client.force_login(self.user)

    def test_default_fee_and_settlement_without_final_chips(self):
        settlement = self.game.calculate_settlement()
        self.assertEqual(self.game.rebuy_fee, 100)
        first = settlement["settlements"][0]
        self.assertEqual(first["rebuy_total"], 300)
        self.assertEqual(first["final_payment"], 1800)
        self.assertEqual(settlement["settlements"][1]["final_payment"], 1000)
        self.assertEqual(settlement["shop_total"], 2500)
        self.assertEqual(sum(row["final_payment"] for row in settlement["settlements"]), 2800)

    def test_variable_fee_and_table_rounding(self):
        self.game.rebuy_fee = 250
        self.game.table_fee = 2001
        self.game.save()
        result = self.game.calculate_settlement()
        self.assertEqual(result["total_rebuy_fee"], 750)
        self.assertEqual(sum(row["table_share"] for row in result["settlements"]), 2001)
        self.assertEqual(sum(row["final_payment"] for row in result["settlements"]), result["shop_total"] + result["total_rebuy_fee"])

    def test_pages_and_registration(self):
        response = self.client.get(reverse("game_detail", args=[self.game.pk]))
        self.assertContains(response, "1回 100 円")
        self.assertContains(response, "最終チップ登録")
        self.assertNotContains(response, "スコア")
        response = self.client.post(reverse("add_rebuy", args=[self.game.pk]), {"count": "2"})
        self.assertRedirects(response, reverse("game_detail", args=[self.game.pk]))
        response = self.client.get(reverse("settlement", args=[self.game.pk]))
        self.assertContains(response, "リバイ料金")
        self.assertContains(response, "2,000")
        self.assertNotContains(response, "チップ収支")
        self.assertEqual(self.game.calculate_settlement()["total_rebuy_fee"], 500)

    def test_forms_and_score_recording(self):
        from .views import GameForm
        form = GameForm()
        self.assertEqual(form.fields["rebuy_fee"].initial, 100)
        self.assertNotIn("chip_rate", form.fields)
        data = {"name": "更新", "date": "2026-10-26", "table_fee": 2000,
                "initial_chips": 1000, "rebuy_chips": 1000, "rebuy_fee": -1,
                "participants": [self.user.pk, self.other.pk]}
        response = self.client.post(reverse("game_edit", args=[self.game.pk]), data)
        self.assertIn("rebuy_fee", response.context["form"].errors)
        self.game.refresh_from_db()
        self.assertEqual(self.game.rebuy_fee, 100)
        data["rebuy_fee"] = 200
        self.assertEqual(self.client.post(reverse("game_edit", args=[self.game.pk]), data).status_code, 302)
        self.game.refresh_from_db()
        self.assertEqual(self.game.rebuy_fee, 200)
        before = self.game.calculate_settlement()
        self.assertEqual(self.client.post(f"/{self.game.pk}/result/", {"final_chips": 999}).status_code, 302)
        self.assertEqual(Result.objects.get(game=self.game, user=self.user).final_chips, 999)
        self.assertEqual(self.game.calculate_settlement(), before)
        self.client.post(f"/{self.game.pk}/result/", {"final_chips": 5000})
        self.assertEqual(Result.objects.get(game=self.game, user=self.user).final_chips, 5000)
        self.assertEqual(self.game.calculate_settlement(), before)


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
