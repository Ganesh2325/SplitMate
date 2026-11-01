from decimal import Decimal

from django.test import SimpleTestCase

from apps.common.allocations import (
    obligations_from_parts,
    pair_effect,
    split_by_shares,
    split_equal,
    split_exact,
    split_itemized,
    split_percentage,
)
from apps.common.exceptions import DomainError
from apps.settlements.simplify import simplify_nets, suggestions_match_nets


class AllocationTests(SimpleTestCase):
    def test_equal_split_assigns_remainder_to_lowest_id(self):
        shares = split_equal(Decimal("100.00"), [3, 1, 2], "INR")
        self.assertEqual(shares[1], Decimal("33.34"))
        self.assertEqual(shares[2], Decimal("33.33"))
        self.assertEqual(shares[3], Decimal("33.33"))
        self.assertEqual(sum(shares.values()), Decimal("100.00"))

    def test_one_rupee_among_three(self):
        shares = split_equal(Decimal("1.00"), [1, 2, 3], "INR")
        self.assertEqual(sum(shares.values()), Decimal("1.00"))
        self.assertEqual(shares[1], Decimal("0.34"))

    def test_exact_and_percentage(self):
        exact = split_exact(Decimal("1000.00"), {1: Decimal("700.00"), 2: Decimal("300.00")}, "INR")
        self.assertEqual(exact[1], Decimal("700.00"))
        percent = split_percentage(Decimal("1000.00"), {1: Decimal("60"), 2: Decimal("40")}, "INR")
        self.assertEqual(percent[1], Decimal("600.00"))
        self.assertEqual(percent[2], Decimal("400.00"))
        with self.assertRaises(DomainError):
            split_percentage(Decimal("100"), {1: Decimal("60"), 2: Decimal("30")}, "INR")

    def test_share_weights(self):
        shares = split_by_shares(
            Decimal("1200.00"),
            {1: Decimal("2"), 2: Decimal("1"), 3: Decimal("1")},
            "INR",
        )
        self.assertEqual(shares[1], Decimal("600.00"))
        self.assertEqual(shares[2], Decimal("300.00"))
        self.assertEqual(shares[3], Decimal("300.00"))

    def test_multiple_payers_preserve_nets(self):
        payers = {1: Decimal("900.00"), 2: Decimal("600.00")}
        shares = {1: Decimal("500.00"), 2: Decimal("500.00"), 3: Decimal("500.00")}
        obligations = obligations_from_parts(payers, shares, "INR")
        nets = {1: Decimal("0"), 2: Decimal("0"), 3: Decimal("0")}
        for user_id in (1, 2, 3):
            paid = payers.get(user_id, Decimal("0"))
            share = shares.get(user_id, Decimal("0"))
            pairwise = sum(
                (pair_effect(obligations, user_id, other) for other in (1, 2, 3) if other != user_id),
                Decimal("0"),
            )
            self.assertEqual(pairwise, paid - share)
            nets[user_id] = pairwise
        self.assertEqual(nets[1], Decimal("400.00"))
        self.assertEqual(nets[2], Decimal("100.00"))
        self.assertEqual(nets[3], Decimal("-500.00"))
        self.assertEqual(sum(nets.values()), Decimal("0"))

    def test_itemized_with_tax_tip_and_discount(self):
        shares, items = split_itemized(
            Decimal("108.00"),
            [
                {"description": "Soup", "quantity": "1", "unit_price": "40", "participant_ids": [1]},
                {"description": "Bread", "quantity": "2", "unit_price": "30", "participant_ids": [1, 2]},
            ],
            "INR",
            tax=Decimal("10.00"),
            tip=Decimal("8.00"),
            discount=Decimal("10.00"),
            adjustment_method="proportional",
        )
        self.assertEqual(sum(item["line_total"] for item in items), Decimal("100.00"))
        self.assertEqual(sum(shares.values()), Decimal("108.00"))
        self.assertGreater(shares[1], shares[2])

    def test_simplify_preserves_prompt_example(self):
        nets = {1: Decimal("-700.00"), 2: Decimal("200.00"), 3: Decimal("500.00")}
        suggestions = simplify_nets(nets, "INR")
        self.assertTrue(suggestions_match_nets(nets, suggestions, "INR"))
        self.assertEqual(len(suggestions), 2)
        self.assertEqual(suggestions[0].debtor_id, 1)
        self.assertEqual(suggestions[0].creditor_id, 3)
        self.assertEqual(suggestions[0].amount, Decimal("500.00"))
