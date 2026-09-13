public static IntegerStamp stampForMask(int bits, long mustBeSet, long mayBeSet) {
        /*
         * Determine if the new stamp created by down & mayBeSet would be contradicting, i.e., empty
         * by definition. This can happen for example if binary logic operations are evaluated
         * repetitively on different branches creating values that are infeasible by definition
         * (logic nodes on phi nodes of false evaluated predecessors).
         */
        if ((mustBeSet & ~mayBeSet) != 0L) {
            return createEmptyStamp(bits);
        }
        return new IntegerStamp(bits, minValueForMasks(bits, mustBeSet, mayBeSet), maxValueForMasks(bits, mustBeSet, mayBeSet), mustBeSet, mayBeSet, true);
    }
