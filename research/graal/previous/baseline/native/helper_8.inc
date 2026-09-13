public static IntegerStamp create(int bits, long lowerBoundInput, long upperBoundInput, long mustBeSetInput, long mayBeSetInput, boolean canBeZero) {
        assert lowerBoundInput >= CodeUtil.minValue(bits) && lowerBoundInput <= CodeUtil.maxValue(bits) : Assertions.errorMessageContext("bits", bits, "lowerBound", lowerBoundInput, "upperBound",
                        upperBoundInput, "mustBeSetInput", mustBeSetInput, "mayBeSetInput", mayBeSetInput, "canBeZero", canBeZero);
        assert upperBoundInput >= CodeUtil.minValue(bits) && upperBoundInput <= CodeUtil.maxValue(bits) : Assertions.errorMessageContext("bits", bits, "lowerBound", lowerBoundInput, "upperBound",
                        upperBoundInput, "mustBeSetInput", mustBeSetInput, "mayBeSetInput", mayBeSetInput, "canBeZero", canBeZero);

        if (isEmpty(lowerBoundInput, upperBoundInput, mustBeSetInput, mayBeSetInput)) {
            return createEmptyStamp(bits);
        }

        long defaultMask = CodeUtil.mask(bits);

        if (mustBeSetInput == 0 && mayBeSetInput == defaultMask && canBeZero) {
            return create(bits, lowerBoundInput, upperBoundInput);
        }

        long lowerBoundCurrent = lowerBoundInput;
        long upperBoundCurrent = upperBoundInput;
        long mustBeSetCurrent = mustBeSetInput;
        long mayBeSetCurrent = mayBeSetInput;

        int iterations = 0;
        while (iterations++ < ITERATION_LIMIT) {

            // Set lower bound, use masks to make it more precise
            long minValue = minValueForMasks(bits, mustBeSetCurrent, mayBeSetCurrent);
            long lowerBoundTmp = Math.max(lowerBoundCurrent, minValue);

            // Set upper bound, use masks to make it more precise
            long maxValue = maxValueForMasks(bits, mustBeSetCurrent, mayBeSetCurrent);
            long upperBoundTmp = Math.min(upperBoundCurrent, maxValue);

            // Compute masks with the new bounds in mind.
            final long boundedMustBeSet;
            final long boundedMayBeSet;
            if (lowerBoundTmp == upperBoundTmp) {
                // For constants the masks are just the value
                boundedMustBeSet = lowerBoundTmp;
                boundedMayBeSet = lowerBoundTmp;
            } else {
                /*
                 * Any high bits that are the same between the upper and lower bound can be used to
                 * refine the mayBeSet and mustBeSet. xor'ing the bounds produces leading zeros for
                 * these bits.
                 */
                int sameBitCount = Long.numberOfLeadingZeros(lowerBoundTmp ^ upperBoundTmp);
                long sameBitMask = -1L >>> sameBitCount;
                boundedMayBeSet = lowerBoundTmp | sameBitMask;
                boundedMustBeSet = lowerBoundTmp & ~sameBitMask;
            }

            long mustBeSetTmp = defaultMask & (mustBeSetCurrent | boundedMustBeSet);
            long mayBeSetTmp = defaultMask & mayBeSetCurrent & boundedMayBeSet;

            // Now recompute the bounds from any adjustments to the may and must masks
            upperBoundTmp = Math.min(upperBoundTmp, maxValueForMasks(bits, mustBeSetTmp, mayBeSetTmp));
            lowerBoundTmp = Math.max(lowerBoundTmp, minValueForMasks(bits, mustBeSetTmp, mayBeSetTmp));

            upperBoundTmp = computeUpperBound(bits, upperBoundTmp, mustBeSetTmp, mayBeSetTmp, canBeZero);
            lowerBoundTmp = computeLowerBound(bits, lowerBoundTmp, mustBeSetTmp, mayBeSetTmp, canBeZero);

            if (lowerBoundTmp > upperBoundTmp || (mustBeSetTmp & (~mayBeSetTmp)) != 0 || (mayBeSetTmp == 0 && (lowerBoundTmp > 0 || upperBoundTmp < 0))) {
                return createEmptyStamp(bits);
            }

            if (lowerBoundCurrent == lowerBoundTmp && upperBoundCurrent == upperBoundTmp && mustBeSetCurrent == mustBeSetTmp && mayBeSetCurrent == mayBeSetTmp) {
                // The values have reached a stable state. If the incoming values are unchanged then
                // this completes in a single pass but if they change then another iteration is
                // performed to ensure the values have stabilized.
                return new IntegerStamp(bits, lowerBoundTmp, upperBoundTmp, mustBeSetTmp, mayBeSetTmp, canBeZero);
            }

            GraalError.guarantee(lowerBoundTmp >= lowerBoundCurrent, "lower bound can't get smaller: %s < %s", lowerBoundTmp, lowerBoundCurrent);
            GraalError.guarantee(upperBoundTmp <= upperBoundCurrent, "upper bound can't get larger: %s > %s", upperBoundTmp, upperBoundCurrent);

            lowerBoundCurrent = lowerBoundTmp;
            upperBoundCurrent = upperBoundTmp;
            mustBeSetCurrent = mustBeSetTmp;
            mayBeSetCurrent = mayBeSetTmp;
        }
        throw GraalError.shouldNotReachHere("More than " + ITERATION_LIMIT + "iterations required to reach a stable stamp");
    }
