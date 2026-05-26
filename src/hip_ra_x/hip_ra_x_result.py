from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hip_ra import HipRaResult


@dataclass
class HipRaXResult:
    result: dict[str, dict[str, dict[str, Any]]]
    caseReportText: str  # pylint: disable=invalid-name

    @staticmethod
    def from_hip_ra_result(hip_ra_result: HipRaResult) -> Any:
        """
        :rtype: HipRaXResult
        """
        with open(hip_ra_result.output_file_path, encoding='UTF-8') as f:
            case_report_text = ''.join(f.readlines())

        result_by_category: dict[str, dict[str, dict[str, Any]]] = {}
        category_split = case_report_text.split('\n      ***')[1:]
        category_split.reverse()  # Put results before inputs, for better UX if UIs are too lazy to sort
        for category_text in category_split:
            lines = category_text.split('\n')
            category_name = lines[0].split('***')[0]
            for k, v in hip_ra_result.result.items():
                if category_name not in result_by_category:
                    result_by_category[category_name] = {}

                if k in category_text:
                    result_by_category[category_name][k] = v

        return HipRaXResult(result=result_by_category, caseReportText=case_report_text)
