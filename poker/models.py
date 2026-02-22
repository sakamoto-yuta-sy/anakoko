from django.db import models
from django.contrib.auth.models import User
from django.db.models import Sum
from decimal import Decimal


class Game(models.Model):
    name = models.CharField(max_length=100)
    date = models.DateField()
    table_fee = models.IntegerField()
    initial_chips = models.IntegerField()
    chip_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )
    rebuy_chips = models.IntegerField()  # 1回あたりのリバイチップ
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    participants = models.ManyToManyField(User, related_name="games")

    def __str__(self):
        return self.name

    def calculate_settlement(self):
        participants = self.participants.all()
        count = participants.count()

        table_share = (
            Decimal(self.table_fee) / Decimal(count)
            if count > 0 else Decimal("0")
        )

        settlements = []
        total_chip_diff = 0
        total_orders = Decimal("0")

        chip_rate = self.chip_rate

        for user in participants:

            order_total = Order.objects.filter(
                game=self,
                user=user
            ).aggregate(total=Sum("price"))["total"] or 0

            total_orders += Decimal(order_total)

            rebuy_count = Rebuy.objects.filter(
                game=self,
                user=user
            ).aggregate(total=Sum("count"))["total"] or 0

            rebuy_total_chips = rebuy_count * self.rebuy_chips
            rebuy_total_money = Decimal(rebuy_total_chips * chip_rate)

            result = Result.objects.filter(
                game=self,
                user=user
            ).first()

            if not result:
                settlements.append({
                    "user": user.username,
                    "unregistered": True
                })
                continue

            initial_chips = self.initial_chips
            total_start_chips = initial_chips + rebuy_total_chips
            final_chips = result.final_chips

            chip_diff = final_chips - total_start_chips
            chip_money = Decimal(chip_diff) * Decimal(self.chip_rate)

            total_chip_diff += chip_diff

            final_payment = (
                    Decimal(order_total)
                    + table_share
                    - chip_money
            )

            settlements.append({
                "user": user.username,
                "initial_chips": initial_chips,
                "rebuy_count": rebuy_count,
                "start_chips": total_start_chips,
                "final_chips": final_chips,
                "chip_diff": chip_diff,
                "chip_money": chip_money,
                "orders": order_total,
                "table_share": table_share,
                "final_payment": final_payment,
                "unregistered": False
            })

        total_table_fee = Decimal(self.table_fee)
        shop_total = total_orders + total_table_fee

        is_balanced = (total_chip_diff == 0)

        return (
            settlements,
            total_chip_diff,
            is_balanced,
            total_orders,
            total_table_fee,
            shop_total
        )


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
