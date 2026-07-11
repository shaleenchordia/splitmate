from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import Expense, Group, GroupMember, Settlement
from .serializers import (
    ExpenseSerializer,
    ExpenseWriteSerializer,
    GroupMemberSerializer,
    GroupSerializer,
    SettlementSerializer,
)
from .services import balances as balance_service


def get_group_for(user, group_id):
    """A user can access a group they created or belong to (via a claimed
    member). Everyone in the flat logs in and sees the same group."""
    group = get_object_or_404(Group, pk=group_id)
    if group.created_by_id == user.id or group.members.filter(user=user).exists():
        return group
    from rest_framework.exceptions import PermissionDenied

    raise PermissionDenied("You are not a member of this group.")


class GroupViewSet(viewsets.ModelViewSet):
    serializer_class = GroupSerializer

    def get_queryset(self):
        u = self.request.user
        return (
            Group.objects.filter(created_by=u) | Group.objects.filter(members__user=u)
        ).distinct()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["get"])
    def balances(self, request, pk=None):
        """Net balance per member + minimal settle-up suggestions."""
        group = get_group_for(request.user, pk)
        net = balance_service.group_net_balances(group)
        members = {m.id: m for m in group.members.all()}
        suggestions = balance_service.suggest_settlements(net)
        return Response(
            {
                "base_currency": group.base_currency,
                "balances": [
                    {
                        "member_id": mid,
                        "name": members[mid].name,
                        "net_minor": n,
                        "is_guest": members[mid].is_guest,
                        "left_on": members[mid].left_on,
                    }
                    for mid, n in sorted(net.items(), key=lambda x: x[1])
                ],
                "settle_up": [
                    {
                        "payer_id": t["payer_id"],
                        "payer": members[t["payer_id"]].name,
                        "payee_id": t["payee_id"],
                        "payee": members[t["payee_id"]].name,
                        "amount_minor": t["amount_minor"],
                    }
                    for t in suggestions
                ],
            }
        )

    @action(detail=True, methods=["get"], url_path="members/(?P<member_id>[0-9]+)/ledger")
    def member_ledger(self, request, pk=None, member_id=None):
        """Every expense line behind one member's balance (Rohan's view)."""
        group = get_group_for(request.user, pk)
        member = get_object_or_404(GroupMember, pk=member_id, group=group)
        entries = balance_service.member_ledger(group, member)
        net = sum(e["effect_minor"] for e in entries)
        return Response(
            {
                "member": GroupMemberSerializer(member).data,
                "entries": entries,
                "net_minor": net,
            }
        )


class GroupMemberViewSet(viewsets.ModelViewSet):
    serializer_class = GroupMemberSerializer

    def get_group(self):
        return get_group_for(self.request.user, self.kwargs["group_pk"])

    def get_queryset(self):
        return self.get_group().members.all()

    def perform_create(self, serializer):
        serializer.save(group=self.get_group())

    def perform_destroy(self, instance):
        if instance.expenses_paid.exists() or instance.splits.exists():
            raise ValidationError(
                "This member has expenses. Set a leave date instead of deleting."
            )
        instance.delete()

    @action(detail=True, methods=["post"])
    def claim(self, request, group_pk=None, pk=None):
        """Link the logged-in user to this member name."""
        member = self.get_object()
        if member.user_id and member.user_id != request.user.id:
            raise ValidationError("Member already claimed by another user.")
        member.user = request.user
        member.save()
        return Response(GroupMemberSerializer(member).data)


class ExpenseViewSet(viewsets.ModelViewSet):
    def get_group(self):
        return get_group_for(self.request.user, self.kwargs["group_pk"])

    def get_queryset(self):
        return (
            Expense.objects.filter(group=self.get_group())
            .select_related("paid_by")
            .prefetch_related("splits__member")
        )

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return ExpenseWriteSerializer
        return ExpenseSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if self.action in ("create", "update", "partial_update"):
            ctx["group"] = self.get_group()
        return ctx

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        expense = serializer.save_expense(self.get_group(), request.user)
        return Response(ExpenseSerializer(expense).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        expense = serializer.save_expense(self.get_group(), request.user, instance=instance)
        return Response(ExpenseSerializer(expense).data)


class SettlementViewSet(viewsets.ModelViewSet):
    serializer_class = SettlementSerializer

    def get_group(self):
        return get_group_for(self.request.user, self.kwargs["group_pk"])

    def get_queryset(self):
        return Settlement.objects.filter(group=self.get_group()).select_related(
            "payer", "payee"
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["group"] = self.get_group()
        return ctx

    def perform_create(self, serializer):
        serializer.save(group=self.get_group(), created_by=self.request.user)
