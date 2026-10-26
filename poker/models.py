from django.db import models
from django.contrib.auth.models import User
from django.db.models import Sum


class Game(models.Model):
    name = models.CharField(max_length=100)
    date = models.DateField()
    table_fee = models.IntegerField()
    initial_chips = models.IntegerField()
    rebuy_fee = models.PositiveIntegerField("リバイ料金（円 / 回）", default=100)
    rebuy_chips = models.IntegerField()  # 1回あたりのリバイチップ
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    participants = models.ManyToManyField(User, related_name="games")

    def __str__(self):
        return self.name

    def calculate_settlement(self):
        participants = list(self.participants.all().order_by("id"))
        count = len(participants)
        # 円単位で割り振り、端数は参加者ID順に1円ずつ加算する。
        base, remainder = divmod(self.table_fee, count) if count else (0, 0)
        settlements = []
        total_orders = 0
        total_rebuy_fee = 0
        for index, user in enumerate(participants):
            order_total = self.order_set.filter(user=user).aggregate(total=Sum("price"))["total"] or 0
            rebuy_count = self.rebuy_set.filter(user=user).aggregate(total=Sum("count"))["total"] or 0
            rebuy_total = rebuy_count * self.rebuy_fee
            table_share = base + (1 if index < remainder else 0)
            total_orders += order_total
            total_rebuy_fee += rebuy_total
            settlements.append({
                "user": user.username, "rebuy_count": rebuy_count,
                "rebuy_total": rebuy_total, "orders": order_total,
                "table_share": table_share,
                "final_payment": order_total + table_share + rebuy_total,
            })
        return {
            "settlements": settlements, "total_orders": total_orders,
            "total_rebuy_fee": total_rebuy_fee, "total_table_fee": self.table_fee,
            "shop_total": total_orders + self.table_fee,
        }


class Order(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    price = models.IntegerField()

    def __str__(self):
        return f"{self.user.username} - {self.name}"


class Rebuy(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    count = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} x {self.count}"



class Result(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    final_chips = models.IntegerField()

    def __str__(self):
        return f"{self.user.username} result"
