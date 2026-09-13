private boolean contains(long value, boolean isCanBeZero) {
        if (value == 0 && !isCanBeZero) {
            /*
             * Special case partially canonicalized graphs and constants: If a guarded pi was
             * created with canBeZero=false but we feed in a constant 0
             */
            if (lowerBound == upperBound && lowerBound == 0) {
                return true;
            }
            return false;
        }
        return value >= lowerBound && value <= upperBound && (value & mustBeSet) == mustBeSet && (value & mayBeSet) == (value & CodeUtil.mask(getBits()));
    }
