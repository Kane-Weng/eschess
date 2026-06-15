// Position evaluation, three levels behind a common interface. 1:1 port of
// python/engine/evaluate.py. Uses double (pawn units) to match the Python
// float scores exactly; positive == White winning.
#pragma once

#include "board.hpp"

class BaseEvaluate {
public:
    virtual ~BaseEvaluate() = default;
    virtual double evaluate(const CBoard &board) const = 0;
};

class SimpleEvaluate : public BaseEvaluate {
public:
    double evaluate(const CBoard &board) const override;
};

class MediumEvaluate : public BaseEvaluate {
public:
    double evaluate(const CBoard &board) const override;
};

class ComplexEvaluate : public BaseEvaluate {
public:
    double evaluate(const CBoard &board) const override;
};
