from rest_framework import serializers

from .models import Expense, ExpenseSplit, Group, GroupMember, Settlement
from .services import splits as split_service


class GroupMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupMember
        fields = ["id", "name", "user", "joined_on", "left_on", "is_guest"]
        read_only_fields = ["user"]


class GroupSerializer(serializers.ModelSerializer):
    members = GroupMemberSerializer(many=True, read_only=True)

    class Meta:
        model = Group
        fields = ["id", "name", "base_currency", "created_at", "members"]


class ExpenseSplitSerializer(serializers.ModelSerializer):
    member_name = serializers.CharField(source="member.name", read_only=True)

    class Meta:
        model = ExpenseSplit
        fields = [
            "member",
            "member_name",
            "share_base_minor",
            "input_percent",
            "input_share_units",
            "input_amount_minor",
        ]


class ExpenseSerializer(serializers.ModelSerializer):
    splits = ExpenseSplitSerializer(many=True, read_only=True)
    paid_by_name = serializers.CharField(source="paid_by.name", read_only=True)

    class Meta:
        model = Expense
        fields = [
            "id",
            "group",
            "description",
            "date",
            "paid_by",
            "paid_by_name",
            "currency",
            "amount_minor",
            "fx_rate",
            "amount_base_minor",
            "split_type",
            "notes",
            "source_batch",
            "source_row_number",
            "splits",
        ]
        read_only_fields = ["group", "amount_base_minor", "source_batch", "source_row_number"]


class ExpenseWriteSerializer(serializers.Serializer):
    """Create/update an expense with its splits in one request.

    participants: [{member_id, percent?, units?, amount_minor?}]
    """

    description = serializers.CharField(max_length=255)
    date = serializers.DateField()
    paid_by = serializers.IntegerField()
    currency = serializers.CharField(max_length=3)
    amount_minor = serializers.IntegerField()
    fx_rate = serializers.DecimalField(max_digits=12, decimal_places=6, default=1)
    split_type = serializers.ChoiceField(choices=Expense.SplitType.choices)
    notes = serializers.CharField(allow_blank=True, required=False, default="")
    participants = serializers.ListField(child=serializers.DictField(), allow_empty=False)

    def validate(self, data):
        group = self.context["group"]
        member_ids = set(group.members.values_list("id", flat=True))
        if data["paid_by"] not in member_ids:
            raise serializers.ValidationError("paid_by is not a member of this group")
        if data["amount_minor"] == 0:
            raise serializers.ValidationError("amount cannot be zero")

        participants = []
        for p in data["participants"]:
            try:
                entry = {"member_id": int(p["member_id"])}
                if "percent" in p:
                    entry["percent"] = p["percent"]
                if "units" in p:
                    entry["units"] = int(p["units"])
                if "amount_minor" in p:
                    entry["amount_minor"] = int(p["amount_minor"])
            except (KeyError, TypeError, ValueError):
                raise serializers.ValidationError("malformed participant entry")
            if entry["member_id"] not in member_ids:
                raise serializers.ValidationError(
                    f"participant {entry['member_id']} is not a member of this group"
                )
            participants.append(entry)

        amount_base_minor = round(data["amount_minor"] * float(data["fx_rate"]))
        try:
            shares = split_service.compute_splits(
                data["split_type"], amount_base_minor, participants
            )
        except split_service.SplitError as e:
            raise serializers.ValidationError(str(e))

        data["participants"] = participants
        data["_amount_base_minor"] = amount_base_minor
        data["_shares"] = shares
        return data

    def save_expense(self, group, user, instance=None):
        data = self.validated_data
        fields = dict(
            group=group,
            description=data["description"],
            date=data["date"],
            paid_by_id=data["paid_by"],
            currency=data["currency"].upper(),
            amount_minor=data["amount_minor"],
            fx_rate=data["fx_rate"],
            amount_base_minor=data["_amount_base_minor"],
            split_type=data["split_type"],
            notes=data.get("notes", ""),
        )
        if instance is None:
            expense = Expense.objects.create(created_by=user, **fields)
        else:
            expense = instance
            for k, v in fields.items():
                setattr(expense, k, v)
            expense.save()
            expense.splits.all().delete()

        for p in data["participants"]:
            ExpenseSplit.objects.create(
                expense=expense,
                member_id=p["member_id"],
                share_base_minor=data["_shares"][p["member_id"]],
                input_percent=p.get("percent"),
                input_share_units=p.get("units"),
                input_amount_minor=p.get("amount_minor"),
            )
        return expense


class SettlementSerializer(serializers.ModelSerializer):
    payer_name = serializers.CharField(source="payer.name", read_only=True)
    payee_name = serializers.CharField(source="payee.name", read_only=True)

    class Meta:
        model = Settlement
        fields = [
            "id",
            "group",
            "payer",
            "payer_name",
            "payee",
            "payee_name",
            "amount_base_minor",
            "date",
            "note",
            "source_batch",
            "source_row_number",
        ]
        read_only_fields = ["group", "source_batch", "source_row_number"]

    def validate(self, data):
        group = self.context["group"]
        member_ids = set(group.members.values_list("id", flat=True))
        if data["payer"].id not in member_ids or data["payee"].id not in member_ids:
            raise serializers.ValidationError("payer and payee must be group members")
        if data["payer"].id == data["payee"].id:
            raise serializers.ValidationError("payer and payee must differ")
        if data["amount_base_minor"] <= 0:
            raise serializers.ValidationError("settlement amount must be positive")
        return data
