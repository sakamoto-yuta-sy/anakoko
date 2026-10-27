from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count
from .models import Game, Order, Rebuy, Result
from django.contrib.auth.models import User
from django import forms
from django.db.models import Max
from django.utils import timezone
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.contrib.auth import update_session_auth_hash
from functools import wraps


def administrator_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not (request.user.is_active and (request.user.is_staff or request.user.is_superuser)):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapped


class ManagedUserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["username"]
        widgets = {"username": forms.TextInput(attrs={"class": "form-control"})}


@administrator_required
def user_create(request):
    form = ManagedUserForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        user.set_password(user.username)
        user.save()
        messages.success(request, f"ユーザー「{user.username}」を作成しました。初期パスワードはユーザー名と同じです。")
        return redirect("user_create")
    return render(request, "user_create.html", {"form": form})


@administrator_required
def user_password_reset(request):
    class ResetForm(forms.Form):
        user = forms.ModelChoiceField(
            queryset=User.objects.order_by("username"), label="対象ユーザー",
            widget=forms.Select(attrs={"class": "form-select"}),
        )

    form = ResetForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        user = form.cleaned_data["user"]
        user.set_password(user.username)
        user.save(update_fields=["password"])
        if user.pk == request.user.pk:
            update_session_auth_hash(request, user)
        messages.success(request, f"ユーザー「{user.username}」のパスワードをユーザー名と同じにリセットしました。")
        return redirect("user_password_reset")
    return render(request, "user_password_reset.html", {"form": form})


# -------------------------
# Forms
# -------------------------

class GameForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["participants"].queryset = User.objects.order_by("username")
        if not self.instance.pk and not self.is_bound:
            self.initial.setdefault("date", timezone.localdate())
        for name, field in self.fields.items():
            if name != "participants":
                field.widget.attrs.update({"class": "form-control"})

    class Meta:
        model = Game
        fields = [
            "name",
            "date",
            "table_fee",
            "initial_chips",
            "rebuy_fee",
            "rebuy_chips",
            "participants",
        ]

        labels = {
            "name": "ゲーム名", "date": "日付", "table_fee": "テーブル代（円）",
            "initial_chips": "初期チップ（pt）", "rebuy_chips": "リバイチップ数（pt）",
            "participants": "参加者",
        }
        widgets = {
            "date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "participants": forms.CheckboxSelectMultiple(),
        }


class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ["name", "price"]
        labels = {"name": "品名", "price": "金額（円）"}
        widgets = {"price": forms.NumberInput(attrs={"inputmode": "numeric"})}


class RebuyForm(forms.ModelForm):
    COUNT_CHOICES = [
        (1, "1"),
        (2, "2"),
        (3, "3"),
    ]

    count = forms.ChoiceField(
        label="リバイ回数",
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

    result = Result.objects.filter(game=game, user=request.user).first()
    order_form = OrderForm()
    rebuy_form = RebuyForm()

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
        "result": result,
        "rebuy_count": rebuy_count,
        "rebuy_total": rebuy_count * game.rebuy_fee,
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
    if not game.participants.filter(pk=request.user.pk).exists():
        raise PermissionDenied


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
    if not game.participants.filter(pk=request.user.pk).exists():
        raise PermissionDenied


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

    form = GameForm(request.POST if request.method == "POST" else None, instance=game)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("game_detail", game_id=game.id)
    return render(request, "game_edit.html", {"game": game, "form": form})


# -------------------------
# 精算表示
# -------------------------

def chip_rows(game):
    rebuys = dict(game.rebuy_set.values("user_id").annotate(total=Sum("count")).values_list("user_id", "total"))
    results = dict(game.result_set.order_by("id").values_list("user_id", "final_chips"))
    ranking = []
    unregistered = []
    for user in game.participants.order_by("username"):
        rebuy_count = rebuys.get(user.pk, 0)
        total_buyin = game.initial_chips + rebuy_count * game.rebuy_chips
        final_chips = results.get(user.pk)
        row = {"user": user.username, "rebuy_count": rebuy_count,
               "total_buyin": total_buyin, "final_chips": final_chips}
        if final_chips is None:
            unregistered.append(row)
        else:
            row["chip_diff"] = final_chips - total_buyin
            ranking.append(row)
    return ranking, unregistered


@login_required
def chip_ranking(request, game_id):
    game = get_object_or_404(Game, pk=game_id)
    ranking, unregistered = chip_rows(game)
    ranking.sort(key=lambda row: -row["chip_diff"])
    previous = None
    rank = 0
    for index, row in enumerate(ranking, start=1):
        if row["chip_diff"] != previous:
            rank = index
        row["rank"] = rank
        previous = row["chip_diff"]
    return render(request, "chip_ranking.html", {
        "game": game, "ranking": ranking, "unregistered": unregistered,
    })


@login_required
def chip_check(request, game_id):
    game = get_object_or_404(Game, pk=game_id)
    registered, missing = chip_rows(game)
    rows = sorted(registered + missing, key=lambda row: row["user"])
    total_buyin = sum(row["total_buyin"] for row in rows)
    total_final = sum(row["final_chips"] for row in registered)
    complete = bool(rows) and not missing
    difference = total_final - total_buyin if complete else None
    return render(request, "chip_check.html", {
        "game": game, "rows": rows, "missing": missing,
        "registered_count": len(registered), "participant_count": len(rows),
        "total_buyin": total_buyin, "total_final": total_final,
        "difference": difference, "reduction": -difference if difference is not None else None,
    })


@login_required
def settlement_view(request, game_id):
    game = get_object_or_404(Game, pk=game_id)

    settlement = game.calculate_settlement()

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
        **settlement,
        "all_orders": all_orders,
    })
