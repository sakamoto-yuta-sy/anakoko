from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count
from .models import Game, Order, Rebuy, Result
from django.contrib.auth.models import User
from django import forms
from django.db.models import Max
from django.utils import timezone
from django.contrib import messages


# -------------------------
# Forms
# -------------------------

class GameForm(forms.ModelForm):
    class Meta:
        model = Game
        fields = [
            "name",
            "date",
            "table_fee",
            "initial_chips",
            "chip_rate",
            "rebuy_chips",
            "participants",
        ]

        widgets = {
            "date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",  # ← これがカレンダー表示
                    "value": timezone.now().date()
                }
            )
        }


class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ["name", "price"]


class RebuyForm(forms.ModelForm):
    COUNT_CHOICES = [
        (1, "1"),
        (2, "2"),
        (3, "3"),
    ]

    count = forms.ChoiceField(
        choices=COUNT_CHOICES,
        widget=forms.Select
    )

    class Meta:
        model = Rebuy
        fields = ["count"]


class ResultForm(forms.ModelForm):
    class Meta:
        model = Result
        fields = ["final_chips"]


# -------------------------
# Game一覧
# -------------------------

@login_required
def game_list(request):
    games = Game.objects.all().order_by("-date")
    return render(request, "game_list.html", {"games": games})


# -------------------------
# Game作成
# -------------------------

@login_required
def game_create(request):
    if request.method == "POST":
        form = GameForm(request.POST)
        if form.is_valid():
            game = form.save(commit=False)
            game.created_by = request.user
            game.save()
            form.save_m2m()
            return redirect("game_detail", game.id)
    else:
        form = GameForm()

    return render(request, "game_create.html", {"form": form})


# -------------------------
# Game詳細（登録まとめ）
# -------------------------

@login_required
def game_detail(request, game_id):
    game = get_object_or_404(Game, id=game_id)

    past_orders = (
        Order.objects
        .values("name")
        .annotate(price=Max("price"))
        .order_by("name")
    )

    orders = Order.objects.filter(
        game=game,
        user=request.user
    ).order_by("-id")

    order_total = (
            Order.objects
            .filter(game=game, user=request.user)
            .aggregate(Sum("price"))["price__sum"]
            or 0
    )

    order_form = OrderForm()
    rebuy_form = RebuyForm()

    result = Result.objects.filter(game=game, user=request.user).first()
    rebuy_count = (
            Rebuy.objects
            .filter(game=game, user=request.user)
            .aggregate(total=Sum("count"))["total"]
            or 0
    )
    context = {
        "game": game,
        "order_form": order_form,
        "rebuy_form": rebuy_form,
        "past_orders": past_orders,
        "rebuy_count": rebuy_count,
        "result": result,
        "orders": orders,
        "order_total": order_total,
    }

    return render(request, "game_detail.html", context)


# -------------------------
# 注文登録
# -------------------------

@login_required
def add_order(request, game_id):
    game = get_object_or_404(Game, pk=game_id)

    past_orders = (
        Order.objects
        .values("name")
        .annotate(price=Max("price"))
        .order_by("name")
    )

    if request.method == "POST":
        form = OrderForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            order.game = game
            order.user = request.user  # ★重要
            order.save()
            messages.success(request, "飲食を登録しました")
            return redirect("game_detail", game.id)
    else:
        form = OrderForm()

    return render(request, "game_detail.html", {
        "game": game,
        "order_form": form,
        "past_orders": past_orders,
    })


# -------------------------
# リバイ登録
# -------------------------

@login_required
def add_rebuy(request, game_id):
    game = get_object_or_404(Game, id=game_id)

    if request.method == "POST":
        form = RebuyForm(request.POST)
        if form.is_valid():
            rebuy = form.save(commit=False)
            rebuy.game = game
            rebuy.user = request.user
            rebuy.save()
            messages.success(request, "リバイを登録しました")

    return redirect("game_detail", game.id)


# -------------------------
# 最終チップ登録
# -------------------------

@login_required
def add_result(request, game_id):
    game = get_object_or_404(Game, id=game_id)

    if request.method == "POST":
        form = ResultForm(request.POST)
        if form.is_valid():
            result, created = Result.objects.update_or_create(
                game=game,
                user=request.user,
                defaults={
                    "final_chips": form.cleaned_data["final_chips"]
                }
            )
            if created:
                messages.success(request, "最終チップを登録しました")
            else:
                messages.success(request, "最終チップを更新しました")

    return redirect("game_detail", game.id)


@login_required
def game_edit(request, game_id):
    game = get_object_or_404(Game, pk=game_id)

    if request.method == "POST":
        game.name = request.POST.get("name")
        game.initial_chips = request.POST.get("initial_chips")
        game.chip_rate = request.POST.get("chip_rate")
        game.rebuy_chips = request.POST.get("rebuy_chips")
        game.table_fee = request.POST.get("table_fee")

        game.save()
        return redirect("game_detail", game_id=game.id)

    return render(request, "game_edit.html", {
        "game": game
    })


# -------------------------
# 精算表示
# -------------------------

@login_required
def settlement_view(request, game_id):
    game = get_object_or_404(Game, pk=game_id)

    (
        settlements,
        total_chip_diff,
        is_balanced,
        total_orders,
        total_table_fee,
        shop_total
    ) = game.calculate_settlement()

    all_orders = (
        Order.objects
        .filter(game=game)
        .values("name")
        .annotate(
            total_qty=Count("name"),
            total_amount=Sum("price")
        )
        .order_by("name")
    )

    return render(request, "settlement.html", {
        "game": game,
        "settlements": settlements,
        "total_chip_diff": total_chip_diff,
        "is_balanced": is_balanced,
        "total_orders": total_orders,
        "total_table_fee": total_table_fee,
        "shop_total": shop_total,
        "all_orders": all_orders,
    })
