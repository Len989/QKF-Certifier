private static long maxValueForMasks(int bits, long mustBeSet, long mayBeSet) {
        if (significantBit(bits, mustBeSet) == 1) {
            // Value is always negative. Maximum value always negative.
            assert significantBit(bits, mayBeSet) == 1 : Assertions.errorMessageContext("bits", bits, "mayBeSet", mayBeSet);
            return CodeUtil.signExtend(mayBeSet, bits);
        } else {
            // Value can be positive or negative. Maximum value always positive.
            return mayBeSet & (CodeUtil.mask(bits) >>> 1);
        }
    }
