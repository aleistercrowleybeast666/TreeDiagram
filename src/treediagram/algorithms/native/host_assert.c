/* Host terminal trap; an assertion is never converted to a successful update.
 * This adapter is not linked into target firmware and does not emulate HAL. */
#include "silverstar_assert.h"
#include <stdio.h>
#include <stdlib.h>

void SilverStarAssert_Fail(SilverStarAssertModuleId module_id,
    const char *file_name, uint32_t line, SilverStarAssertReasonId reason_id)
{
    fprintf(stderr, "SilverStar host assertion %u:%u at %s:%u\n",
        (unsigned)module_id, (unsigned)reason_id, file_name, (unsigned)line);
    abort();
}

void SilverStarAssert_Check(uint8_t condition, SilverStarAssertModuleId module_id,
    const char *file_name, uint32_t line, SilverStarAssertReasonId reason_id)
{
    if (condition == 0U) { SilverStarAssert_Fail(module_id, file_name, line, reason_id); }
}

void SilverStarAssert_ObjectCheck(const volatile void *object, uint32_t alignment,
    SilverStarAssertModuleId module_id, const char *file_name, uint32_t line)
{
    if ((object == NULL) || (alignment == 0U) || (((uintptr_t)object % alignment) != 0U))
    { SilverStarAssert_Fail(module_id, file_name, line, SILVERSTAR_ASSERT_REASON_NULL_POINTER); }
}
