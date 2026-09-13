private static long setOptionalBits(int bits, long bound, long mustBeSet, long mayBeSet, long initialValue) {
        final long optionalBits = mayBeSet & ~mustBeSet & CodeUtil.mask(bits - 1);
        assert (initialValue & optionalBits) == 0 : Assertions.errorMessageContext("bits", bits, "bound", bound, "mustBeSet", mustBeSet, "mayBeSet", mayBeSet, "initialValue", initialValue);
        long value = initialValue;
        for (int position = bits - 1; position >= 0; position--) {
            long bit = 1L << position;
            if ((bit & optionalBits) != 0 && (value | bit) <= bound) {
                value |= bit;
            }
        }
        return value;
    }
